import random
from pymongo import MongoClient

''' MongoDB 测试 '''
__author__ = 'jarod zhao'

'''
MongoDb 库名及表名
mydb.test.find()
'''
db_addr = '127.0.0.1'
conn = MongoClient(db_addr, 27017)
db = conn.mydb


# 更新多条记录，不用 mulit ?!
# db.test.update_many({'name': 'jarod zhao'},{'$set':{'age': 100}})

my_set = db.test.find({'$or':[{'name': 'jarod zhao'},{'email':'3245121@qq.com'}]},{'age':1})
for rs in my_set:
	print(rs)


