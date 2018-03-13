from pymongo import MongoClient

conn = MongoClient('localhost', 27017)
db = conn.smzdm

faxian = db.faxian.find().count()
comment = db.comment.find().count()

print('faxian=%s comment=%s' % (faxian, comment))

