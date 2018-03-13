import datetime
from pymongo import MongoClient
from urllib import request
from get_faxian_comments import *                       # 评论信息
from get_faxian_ext import *                            # Item 扩展信息

last_data = []
at_first = True


def get_html(page):
    '''
    抓取 HTML 源方法
    '''
    url = 'https://faxian.smzdm.com/p' + str(page)
    headers = {'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36'}

    r = requests.get(url, headers=headers)
    content = bsp(r.text, 'html.parser')

    ul_html = content.find('ul', id='feed-main-list')
    li_html = ul_html.find_all('li')

    return li_html


def get_last_data():
    '''
    获取库中的最新时间戳的item.url属性字符串列表、item.time_
    可能存在同一时间多条记录，url 需要保存多条，所以 urls 是一个列表
    因为 time_ 值都相同，所以保存一条即可
    '''
    conn = sqlite3.connect('smzdm.db')
    cursor = conn.cursor()
    
    global last_data
    urls = []
    
    #除非是空数据库，否则一定会返回记录集
    sql = 'SELECT time_, url FROM faxian WHERE time_ = (SELECT time_ FROM faxian ORDER BY id_ LIMIT 1)'
    
    try:
        rs = cursor.execute(sql)
        for row in rs:
            urls.append(row[1])
        
        # 需要把 02-17 18:34 这样的时间转换一下
        last_data = [get_time_stamp(row[0]), urls]
    except UnboundLocalError:
        last_data = [time.time(), '']
    except sqlite3.OperationalError:
        last_data = [time.time(), '']
    finally:
        conn.close()
    
    return last_data


def mongodb_has_item(item):
    '''mongodb 是否包含该 item '''
    conn = MongoClient('localhost', 27017)
    db = conn.smzdm

    rs = db.faxian.find({'url':item['url']})

    if rs.count() < 1:
        return 0
    elif rs[0]['first'] == 1:
        return 2
    else:
        return 1

    # if rs.count() > 0 and rs[0].get('first') == 1:
    #   return 2
    # elif rs.count() > 0:
    #   return 1
    # else:
    #   return 0

    # 2: 查找到当前记录是头条记录
    # 1: 数据库中包含本记录
    # 0: 新纪录，保存


def has_item(item):
    '''
    根据 item.title 判断库中是否已有该记录
    '''
    conn = sqlite3.connect('smzdm.db')
    cursor = conn.cursor()

    sql = "select first from faxian where url = ?"
    try:
        result = cursor.execute(sql, (item.url,)).fetchall()          #坑一，使用占位符，记得在值后面加 ,
        if len(result) > 0 and result[0][0] == 1:                       #坑二，不调用 fetchall() 方法，返回的数量始终为 -1
            return 2
        elif len(result) > 0:                                           #坑三，翻页后，前页的记录出现在本页 = 1 的记录都被作为重复记录忽略了！！
            return 1
        else:
            return 0
    except:
        pass    #首次运行时会引发异常，找不到表（刚刚建的库，没有表！）
    finally:
        conn.close()

    return 0


def save_img(img_url, url):
    '''
    保存图片文件到 images
    每天保存一个目录
    '''

    #https://qny.smzdm.com/201802/25/5a92aef47d5b91309.jpg_d200.jpg
    
    local_name = url.split('/')
    local_name.pop()
    fn = local_name.pop() + '.jpg'
    
    request.urlretrieve(img_url, 'images/' + fn)


def get_time_stamp(str_time):
    '''
    根据数据库中日期字符串生成格式化后的日期和时间
    格式：2018-02-19 2:26:00
    '''
    timer = str(datetime.datetime.now().year) + '-' + str_time + ':00'
    return time.mktime(time.strptime(timer, '%Y-%m-%d %H:%M:%S'))


def go_loop():
    '''页面开始，向下顺序执行
    外层循环：第 x 页'''
    goon = True #是否继续循环，默认值继续
    
    for page in range(1000): #1000页为能获取到的最大页码
        #库中最晚时间戳的对象列表
        last_data = get_last_data()
        #等待几秒后继续下一页
        wait = int(random.random() * 10) + 5
        page += 1
        
        # goon 的返回值问题？！！
        if not fetch_data(page, wait, last_data):
            '''
            如果抓取到的记录库中已有，并且有特殊标记的记录
            没有特殊标记的，视为本次抓取中的重复记录，自动忽略
            '''
            goon = False
            break
        
        #抓取完一页，等待几秒后再继续
        time.sleep(wait)
    
    return goon


def fetch_data(page, wait, last_data):
    '''
    分离业务的逻辑过程
    '''
    html = get_html(page)
    
    #开始抓取 smzdm.faxiam
    for li in html:
        in_db_result = False    #每条记录写库前初始化写库结果为 False，写库成功后更新为 True
        item = fetch_item(li) #分离出商品条目信息（对于页面中确实两条一样的记录，是否作为两个对象处理？）

        '''
        如何辨别分离出来的这个 item 是抓上一页数据时存入库中的
        还是上一次抓取到的数据（如果是上次抓的，那应该是上次最早抓到的一条记录）
        方案： 每次开始抓取数据时，抓到的第一条记录特别标记一下！
              此种方案是否可以解决问题？！
              如若可行，表中增加一个字段，抓取到的首条记录保存时间（或标
              识）之后抓取的记录保存为0（或者null)
        每次写库，更新 write_time
        写库时检察上次时间，如果超过 3600 秒则认为是一次新的抓取开始
        
        使用全局变量 last_data[0] 保存最后写库时间，只要程序一直运行，该值就一直存在
        1.暂停xxxx秒后，该值依然存在并可继续使用
        2.重新启动后（停止后的重启），该值为数据库中的最新时间戳
        last_data 保存的时间戳为全局变量，所以该列表不能重新赋值，只能更新内容！！
        '''
        # 头条记录标识
        global at_first
        if at_first:
            #print('头条记录...\n')
            item['first'] = 1      #本次抓取的头条记录
        else:
            item['first'] = 0      #本次抓取的非头条记录

        '''
        重复记录比对：
            1.抓到的头条记录需要比对：
              a-是否在 last_data[1] 列表中
              b-库中是否存在？可能性很小，但有
            2.抓取的非头条记录
              a-库中是否存在？
            需要写一个方法，检测 item 是否存在 has_item(item)
        '''

        db_has_item = mongodb_has_item(item) # True or False
        # print(db_has_item == 0)
        '''
        if 是头条记录：
            if 库中无：
                写入库中
            else 库中有：
                已抓取自上次操作后的所有数据
        else 不是头条记录：
            if 库中无：
                写入库中
            else 库中有
                重复了？！忽略！
        if 头条记录 and 库中有:
            以获取所有信息，暂停
        elif 头条记录 and 库中无：
            入库，并提示
        elif 非头条 and 库中有：
            已存在，忽略
        elif 非头条 and 库中无:
            入库，并提示
        else:
            有无其他情况?
        ========================
        if 库中无：
            入库，并提示
        else:
            if 头条记录：
                已抓取所有
            elif 非头条:
                已存在，忽略
        ========================
        '''

        #print('at_first=%s  db_has_item=%s\n' % (at_first, db_has_item))
        # if 1 == 0:
        if db_has_item == 0:
	        # 新记录
            in_mongodb(item)
            print('%s | %s\n%s %s %s 评：%s\n%s %s\n%s\n%s' % (item['item_type'], item['title'], item['store'], item['price'], item['time_'], item['comments'],
            item['user_'], item['user_url'], item['desc'], item['url']), end='\n ------------------------ \n')
	        
            # 保存扩展信息
            # fetch_ext(item.ext)
	        
            # 保存评论信息（根据条目的地址跳转到抓取评论）
            get_comment(item['url'])
        else:
            if db_has_item == 2:
                timer = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                print('已获取到截止上次操作后的所有数据！\n最后获取记录：\n%s at [%s]' % (item['title'], timer))
                return False
                break   #跳出循环
            else:   #---------------------------------------------- 判断仍有问题，遗漏很多记录--------被作为已存在处理，复查后发现没有遗漏~
                print('%s | %s\n%s %s %s 评：%s\n%s %s\n%s\n%s\n-------------该条目已存在，自动忽略!!!-------------' % (item['item_type'],
                 item['title'], item['store'], item['price'], item['time_'], item['comments'], item['user_'], item['user_url'], item['desc'], item['url']), end='\n-\n')


        # if item.first == 1:
        #     if not db_has_item:
        #     else:
        #         timer = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        #         print('已获取到截止上次操作后的所有数据！\n最后获取记录：\n%s at [%s]' % (item.title, timer))
        #         return False
        #         break   #跳出循环
        # else:
        #     if not db_has_item:
        #         in_db(item)
        #         print('%s | %s\n%s %s %s 评：%s\n%s %s\n%s\n%s' % (item.item_type, item.title, item.store, item.price, item.time_, 
        #             item.comments, item.user_, item.user_url, item.desc, item.buy_link), end='\n-\n')
        #     elif db_has_item:   #翻页后，出现判断错误！
        #         timer = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        #         print('已获取到截止上次操作后的所有数据！\n最后获取记录：\n%s - %s' % (item.title, timer))
        #         return False
        #         break   #跳出循环
        #     else:
        #         print('%s | %s\n%s %s %s 评：%s\n%s %s\n%s\n%s\n-------------该条已存在，自动忽略!!!-------------' % (item.item_type, item.title,
        #             item.store, item.price, item.time_, item.comments, item.user_, item.user_url, item.desc, item.buy_link), end='\n-\n')

        # 入库后需要返回两个结果：
        # 1.入库标识，记录是否写入库中 
        # 2.最后写库时间，需要保持在页面级的变量中
        # 写库操作只返回一个 boolean 为 True 的值，写库过程中更新最后写库时间到全局变量 last_data 中

    # 页面抓取完成，等候 x 秒后继续...
    print('***************************************** 第 %s 页, 等待 %s 秒继续下一页... **************************************************\n' % (page, wait))
    return True


def fetch_item(html):
    '''
    分离对象过程，改为 dict 类型
    '''
    item = {}

    # item.id_ = time.time()
    item['my_id'] = time.time()

    #1 div
    feed_block_ver = html.find('div', class_='feed-block-ver')

    #2 div 类别信息（可选）
    feed_ver_pic = html.find('div', class_='feed-ver-pic')
    tag = feed_ver_pic.find('span')
    if tag != None:
        # item.item_type = tag.text
        item['item_type'] = tag.text
    else:
        # item.item_type = 'no'
        item['item_type'] = ''

    #2 h5 标题和zdm_url
    h5 = html.find('h5')
    # item.title = h5.find('a').text
    item['title'] = h5.find('a').text

    # item.url = h5.find('a')['href']
    item['url'] = h5.find('a')['href']

    #  电商
    mall = html.find('a', class_='tag-bottom-right')
    # item.store = mall.text
    item['store'] = mall.text

    #2 div 价格
    z_highlight = html.find('div', class_='z-highlight')
    # item.price = z_highlight.text.strip()
    item['price'] = z_highlight.text.strip()

    #2 span 用户信息
    feed_ver_row = html.find('div', class_='feed-ver-row')

    if feed_ver_row.find('div', 'feed-ver-row-l') != None:
        feed_ver_row_l = feed_ver_row.find('div', class_='feed-ver-row-l')

        if feed_ver_row_l.find('span', class_='z-avatar-group') != None:
            z_avatar_group = feed_ver_row_l.find('span', class_='z-avatar-group')

            if z_avatar_group.find('a', class_='z-avatar-name') != None:
                # item.user_ = z_avatar_group.find('a', class_='z-avatar-name').text.strip() #正常用户信息
                item['user_'] = z_avatar_group.find('a', class_='z-avatar-name').text.strip() #正常用户信息

                # item.user_url = z_avatar_group.find('a', class_='z-avatar-name')['href']
                item['user_url'] = z_avatar_group.find('a', class_='z-avatar-name')['href']
            else:
                # item.user_ = z_avatar_group.text.strip()
                item['user_'] = z_avatar_group.text.strip()

                # item.user_url = '推广信息，无用户信息'
                item['user_url'] = '推广信息，无用户信息'

        else:
            # item.user_ = feed_ver_row_l.text.strip()
            item['user_'] = feed_ver_row_l.text.strip()

            # item.user_url = 'b#'
            item['user_url'] = 'b#'
    else:
        # item.user_ = '商家自荐'   #根本没有用户信息
        item['user_'] = '商家自荐'   #根本没有用户信息

        # item.user_url = '无用户信息'
        item['user_url'] = '无用户信息'

    feed_ver_row_r = html.find_all(class_='feed-ver-row-r')

    for tag in feed_ver_row_r:  #这里会有两个 feed-ver-row-r，不包含 feed-link-btn 属性的标签即为时间
        if tag.find('div', class_='feed-link-btn') == None:
            time_ = tag.text
    # item.time_ = time_
    if time_.find('-') == -1:
        today = time.strftime('%m-%d ', time.localtime())
        # item.time_ = today + time_
        item['time_'] = today + time_
    else:
        # item.time_ = time_
        item['time_'] = time_

    #2 div 描述信息
    feed_ver_descripe = html.find('div', class_="feed-ver-descripe")
    # item.desc = feed_ver_descripe.text.strip()
    item['desc'] = feed_ver_descripe.text.strip()

    #5 span 值 zhi
    unvoted_wrap = html.find('span', class_='unvoted-wrap')
    # item.zhi = unvoted_wrap.find('span').text
    item['zhi'] = unvoted_wrap.find('span').text

    #5 i 评论数
    comments = html.find('i', class_='z-icon-comment')
    # item.comments = comments.find_parent().text
    item['comments'] = comments.find_parent().text

    # 购买链接
    link = html.find('div', class_='feed-link-btn').find('a')
    # item.buy_link = link['href']
    item['buy_link'] = link['href']

    # 图片信息
    img_html = html.find('div', class_='feed-ver-pic').find('a').find('img')
    img_url = img_html['src']
    # item.img_url = img_url
    item['img_url'] = img_url

    save_img(img_url, item['url'])

    # 扩展信息
    item['ext'] = link['onclick']

    return item


def in_mongodb(item):
	'''插入到数据库 mongodb'''
	conn = MongoClient('localhost', 27017)
	db = conn.smzdm

	fx_set = db.faxian
	fx_set.insert(item)

	global at_first
	at_first = False # 写入第一条记录后标识改为 False


def in_db(item):
    '''
    插入对象到数据库 sqlite3
    '''
    conn = sqlite3.connect('smzdm.db')
    cursor = conn.cursor()
    cursor.execute('create table if not exists faxian (id_, first, item_type, title, price, store, time_, url, user_, user_url, desc, zhi, comments, buy_link, img_url)')

    sql = 'insert into faxian values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
    cursor.execute(sql, (item.id_, item.first, item.item_type, item.title, item.price, item.store, item.time_, item.url, item.user_, item.user_url, item.desc, 
        item.zhi, item.comments, item.buy_link, item.img_url))

    global at_first
    at_first = False

    conn.commit()
    conn.close()

    #最后写库时间更新
    global last_data
    last_data[0] = time.time()

    return True


if __name__ == '__main__':
    item = Item
    while go_loop() == False:
        print('\n暂停 %s 秒后重新开始...\n' % int(item.next_time))
        time.sleep(item.next_time)

        at_first = True