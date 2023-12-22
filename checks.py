import os
from datetime import datetime

# Posts
print("POST CHECKS")

# Episode Number in Title
problem = False
for post_name in os.listdir("_posts/"):
    num = int(post_name[:-3].split('-')[-1])
    with open("_posts/" + post_name) as post:
        for line in post:
            if "title:" in line and num != 110:
                if int(line.split()[2][:-1]) != num:
                    problem = True
print (("❌" if problem else "✅") + " - Episode Number in Title")

# Episode Number in Link to Website (Text)
problem = False
for post_name in os.listdir("_posts/"):
    num = int(post_name[:-3].split('-')[-1])
    with open("_posts/" + post_name) as post:
        idx = 3 if num < 115 else 4
        for line in post:
            if "Link to Episode" in line:
                if int(line.split()[idx]) != num:
                    problem = True
print (("❌" if problem else "✅") + " - Episode Number in Link to Website (Text)")

# Date in Link to Website (Link)
problem = False
for post_name in os.listdir("_posts/"):
    date = post_name[:10]
    with open("_posts/" + post_name) as post:
        idx = 3 if num < 115 else 4
        for line in post:
            if "Link to Episode" in line:
                if '-'.join(line.split('/')[3:6]) != date:
                    problem = True
print (("❌" if problem else "✅") + " - Date in Link to Website (Link)")

# Date in Release Date
problem = False
for post_name in os.listdir("_posts/"):
    date = post_name[:10]
    with open("_posts/" + post_name) as post:
        idx = 3 if num < 115 else 4
        for line in post:
            if "Date Released:" in line:
                if line.strip().split()[-1] != date:
                    problem = True
print (("❌" if problem else "✅") + " - Date in Release Date")

# Discussion Link Issue Number
problem = False
for post_name in os.listdir("_posts/"):
    num = int(post_name[:-3].split('-')[-1])
    with open("_posts/" + post_name) as post:
        for line in post:
            if "Discuss this episode" in line:
                # Ep 115 started with Issue 5 (so subtract 110)
                if num - 110 + (num > 116) + (num > 151) != int(line[:-2].split('/')[-1]):
                    problem = True
print (("❌" if problem else "✅") + " - Discussion Link Issue Number")

# Dates Differ by 7 Days
problem = False
dates = []
for post_name in os.listdir("_posts/"):
    date = post_name[:10]
    dates.append(datetime.strptime(date, "%Y-%m-%d"))
dates.sort()
for a, b in zip(dates[:-1], dates[1:]):
    if (b - a).days != 7:
        problem = True
print (("❌" if problem else "✅") + " - Dates Differ by 7 Days")

# Episodes
print("EPISODES CHECKS")

# Number, Title & Link in Episodes.md
problem_title      = False
problem_date       = False
problem_link_date  = False
problem_link_num   = False
for post_name in os.listdir("_posts/"):
    num  = int(post_name[:-3].split('-')[-1])
    date = post_name[:10]
    with open("_posts/" + post_name) as post:
        for line in post:
            if "title:" in line:
                title = ' '.join(line.split("\"")[-2].split()[2:])
    with open("pages/episodes.md") as file:
        for n, line in enumerate(file):
            if n > 10:
                data = line.split("|")
                if len(data) > 3:
                    other_num   = int(data[1].strip())
                    other_date  = data[-2].strip()
                    other_title = data[2].split("]")[0].strip()[1:].replace('`', '')
                    link_num    = int(data[2].split(']')[1].split("/")[6].strip()[8:-6])
                    link_date   = '-'.join(data[2].split(']')[1].split("/")[3:6])
                    
                    if num == other_num:
                        if date != other_date:
                            problem_date = True
                        if title != other_title and 'Ben Deane' not in title:
                            print(title)
                            print(other_title)
                            problem_title = True
                        if date != link_date:
                            problem_link_date = True
                        if num != link_num:
                            problem_link_num = True

print (("❌" if problem_date      else "✅") + " - Episode Date")
print (("❌" if problem_title     else "✅") + " - Episode Title")
print (("❌" if problem_link_date else "✅") + " - Episode Date in Link")
print (("❌" if problem_link_num  else "✅") + " - Episode Number in Link")
