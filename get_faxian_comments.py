from pymongo import MongoClient
from bs4 import BeautifulSoup as bsp
import time
import random
import requests

from FaxianItem import *								# 优惠信息对象导入

'''
抓取 HTML 源方法
'''
def get_html(url):
	tag = ("section", "comments")
	
	headers = {'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36'}
	r = requests.get(url, headers=headers)
	page_html = bsp(r.text, 'html.parser')

	html = page_html.find(tag[0], id=tag[1])
	return (html, url)

'''
分离评论过程
'''
def fetch_data(html):

	#寻找页码信息，然后循环页码获取所有评论
	page_count = 1 #初始值设为1 ，当只有一页评论时能保存循环抓取至少循环一次
	page_area_html = html[0].find('ul', class_='pagination')
	if page_area_html != None:

		pagedown_html = page_area_html.find('li', class_='pagedown')
		if pagedown_html != None:
			#为何向前找没有换行符？！
			#末页显示有问题：因为末页没有下一页了！
			#查找到'上一页'按钮，如果按钮后一个标签内容为 1, 可以断定为当前页是末页
			page_count_html = pagedown_html.previous_sibling.find('a')
			page_count = page_count_html.text
		# else:
		# 	page_count = 1	#初始值设为1 ，当只有一页评论时能保存循环抓取至少循环一次

	ul_html = html[0].find('ul', class_='comment_listBox')

	if ul_html != None:			# ul_html = None 表示该页面没有评论

		li_html = ul_html.find_all("li", class_='comment_list')

		# 开始循环抓取所有评论
		comments = []

		for li in li_html:
			# 评论楼层
			floor_html = li.find('div', class_='comment_avatar')
			floor = floor_html.find('span').text

			if floor == '沙发':
				floor = '1'
			elif floor == '椅子':
				floor = '2'
			elif floor == '板凳':
				floor = '3'
			else:
				floor = floor.replace('楼', '')

			# 评论人
			user_html = li.find('div', class_='comment_conBox')
			user_ = user_html.find('a', class_='a_underline').find('span').text
			user_url = user_html.find('a', class_='a_underline')['href']

			# 评论时间
			time_ = user_html.find('div', class_='time').text	#发表时间，需要用当前时间去计算出来
			now = time.time()
			
			# 用户等级
			rank_html = user_html.find('div', class_='rank')
			if rank_html != None:
				user_level = rank_html['title'].replace('级', '')
			else:
				user_level = ''	#无用户等级，新用户？

			# 引用评论，保存楼层编号
			quote_html = li.find('div', class_='blockquote_wrap')

			quote = []
			quote_ = ''

			if quote_html != None:
				quote_s_html = quote_html.find_all('blockquote', class_='comment_blockquote') 

				for i in quote_s_html:
					# floor 引用的楼层编号
					quote.append(i.find('div', class_='comment_floor').text) #提取引用的评论编号

				if len(quote) > 0:
					quote_ = ','.join(str(n) for n in quote)

			# 评论内容主体
			# content_html = li.find('div', class_='comment_conBox')
			# blockquote_html = content_html.find('div', class_='blockquote_wrap')
			# if blockquote_html == None:
			# 	content = content_html.find('div', class_='comment_conWrap').find('span').text
			# else:
			# 	# 有引用评论
			# 	content = blockquote_html.next_sibling.next_sibling.find('span').text
			content_html = li.find_all('span', itemprop="description")
			comment_ = content_html[len(content_html)-1].text

			# 顶，踩，终端类型
			comment_action_html = li.find('div', class_='comment_conWrap').find('div', class_='comment_action')
			if comment_action_html.find('span', class_='come_from') != None:
				platform = comment_action_html.find('span', class_='come_from').find('a').text.replace(' 客户端', '')
			else:
				platform = 'PC'
			ding = comment_action_html.find('a', class_='dingNum').find('span').text.replace('(', '').replace(')', '')
			cai = comment_action_html.find('a', class_='caiNum').find('span').text.replace('(', '').replace(')', '')

			item_url = html[1]

			id_ = time.time()

			# comment = Comment(id_, floor, user_, user_level, user_url, time_, quote_, content, platform, item_url, ding, cai)
			comment = ({'id_':id_, 'floor':floor, 'user_':user_, 'user_level':user_level, 'user_url':user_url, 'time_':time_,
			 'comment_':comment_, 'platform':platform, 'item_url':item_url, 'ding':ding, 'cai':cai})

			# 生成评论列表
			comments.append(comment)

		return (page_count, comments)

	return None



def in_mongodb(comment):
	'''存入 mongoDB 数据库'''
	conn = MongoClient('localhost', 27017)
	db = conn.smzdm

	c_set = db.comment
	c_set.insert(comment)


'''
入库操作
'''
def in_db(comment):
	try:
	    conn = sqlite3.connect('smzdm.db')
	    cursor = conn.cursor()
	    cursor.execute('create table if not exists comment (id_, floor, user_, user_level, user_url, time_, quote, comment_, platform, item_url, ding, cai)')

	    sql = 'insert into comment values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
	    cursor.execute(sql, (comment.id_, comment.floor, comment.user_, comment.user_level, comment.user_url, comment.time_, comment.quote, comment.comment_,comment.platform, comment.item_url, comment.ding, comment.cai))

	    conn.commit()
	except Exception as e:
		raise e
	finally:
		cursor.close()
		conn.close()
'''
模块化循环过程，便于其他地方调用
'''
def get_comment(url):
	html = get_html(url)			#返回整个页面的 html
	fetch_result = fetch_data(html) #返回分离出来的结果 (page_count, comments) 或者 None

	if fetch_result != None: # 无评论，不循环

		page_count = fetch_result[0]

		for p in range(1, int(page_count) + 1):
			url_p = url + 'p' + str(p)
			p_html = get_html(url_p)

			if p == 1:
				comments = fetch_result[1]
			else:
				comments = fetch_data(p_html)[1]

			for comment in comments:
				print('-')
				print(comment['floor'])
				print(comment['user_'])
				print(comment['user_level'])
				print(comment['user_url'])
				print(comment['time_'])
				# print(comment['quote'])
				print(comment['comment_'])
				print(comment['platform'])
				print(comment['item_url'])
				print('顶：%s  踩：%s' % (comment['ding'], comment['cai']))
				in_mongodb(comment)

			print('------------------第 %s 页，总 %s 页--------------------------' % (p, page_count))

			if p != int(page_count):
				print('等待 %s 秒后继续抓取下一页评论' % (5 + int(random.random() * 10)))
				time.sleep(5)
	else:
		print('该页面没有评论\n')

if __name__ == '__main__':
	url = 'https://www.smzdm.com/p/8808292/'
	get_comment(url)
