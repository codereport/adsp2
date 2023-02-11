import os

## Posts
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
                    print(post_name + " ➡️ " + line.strip().split()[-1]) 
                    problem = True
print (("❌" if problem else "✅") + " - Date in Release Date")

# TODO

# Posts
# =====
# - File names
# - Link to GitHub Discussion (after Episode 115)

# Episodes 
# ========
# - Date and Title match
