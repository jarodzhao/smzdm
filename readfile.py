import re

file = open('wifi_config.log', 'r')

lines = file.readlines()

for line in lines:
	print(line)