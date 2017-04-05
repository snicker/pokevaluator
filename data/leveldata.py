import csv
import os

csvfile = os.path.join(os.path.dirname(os.path.realpath(__file__)),'leveldata.csv')
LEVELDATA = {}

with open(csvfile) as f:
    reader = csv.reader(f)
    headerrow = reader.next()
    for row in reader:
        data = {}
        for i, column in enumerate(headerrow):
            data[column] = row[i]
        LEVELDATA[int(data['level'])] = data