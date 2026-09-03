import os
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

# Posts
print("POST CHECKS")

# Episode Number in Title
problem = False
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    num = int(post_name[:-3].split("-")[-1])
    with open("_posts/" + post_name) as post:
        for line in post:
            if "title:" in line and num != 110 and num != 200:
                if int(line.split()[2][:-1]) != num:
                    problem = True
print(("❌" if problem else "✅") + " - Episode Number in Title")

# Episode Number in Link to Website (Text)
problem = False
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    num = int(post_name[:-3].split("-")[-1])
    with open("_posts/" + post_name) as post:
        idx = 3 if num < 115 else 4
        for line in post:
            if "Link to Episode" in line:
                if int(line.split()[idx]) != num:
                    problem = True
print(("❌" if problem else "✅") + " - Episode Number in Link to Website (Text)")

# Date in Link to Website (Link)
problem = False
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    date = post_name[:10]
    with open("_posts/" + post_name) as post:
        idx = 3 if num < 115 else 4
        for line in post:
            if "Link to Episode" in line:
                if "-".join(line.split("/")[3:6]) != date:
                    problem = True
print(("❌" if problem else "✅") + " - Date in Link to Website (Link)")

# Date in Release Date
problem = False
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    date = post_name[:10]
    with open("_posts/" + post_name) as post:
        idx = 3 if num < 115 else 4
        for line in post:
            if "Date Released:" in line:
                if line.strip().split()[-1] != date:
                    problem = True
print(("❌" if problem else "✅") + " - Date in Release Date")

# Discussion Link Issue Number
problem = False
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    num = int(post_name[:-3].split("-")[-1])
    with open("_posts/" + post_name) as post:
        for line in post:
            if "Discuss this episode" in line:
                # Ep 115 started with Issue 5 (so subtract 110)
                actual_num = (
                    num
                    - 110
                    + (num > 116)
                    + (num > 151)
                    + ((num > 181) * 3)
                    + ((num > 184) * 4)
                    + ((num > 260))
                    + ((num > 269))
                    + ((num > 274))
                )
                if actual_num != int(line[:-2].split("/")[-1]):
                    print(num, actual_num, int(line[:-2].split("/")[-1]))
                    problem = True
print(("❌" if problem else "✅") + " - Discussion Link Issue Number")

# Dates Differ by 7 Days
problem = False
dates = []
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    date = post_name[:10]
    dates.append(datetime.strptime(date, "%Y-%m-%d"))
dates.sort()
for a, b in zip(dates[:-1], dates[1:]):
    if (b - a).days != 7:
        problem = True
print(("❌" if problem else "✅") + " - Dates Differ by 7 Days")

# Unique Buzzsprout IDs
problem = False
buzzsprout_ids = {}
for post_name in sorted(os.listdir("_posts/")):
    if not post_name.endswith(".md"):
        continue
    with open("_posts/" + post_name) as post:
        for line in post:
            if line.startswith("buzzsprout-id:"):
                bid = line.split(":")[1].strip()
                if bid in buzzsprout_ids:
                    if not problem:
                        print("❌ - Unique Buzzsprout IDs")
                    print(f"  Duplicate buzzsprout-id {bid}: {buzzsprout_ids[bid]} and {post_name}")
                    problem = True
                else:
                    buzzsprout_ids[bid] = post_name
                break
if not problem:
    print("✅ - Unique Buzzsprout IDs")

# No Unknown Speakers in Buzzsprout Transcripts
transcript_cache_path = ".transcript-check-cache"
try:
    with open(transcript_cache_path) as cache:
        passed_transcript_ids = {
            line.strip() for line in cache if line.strip().isdigit()
        }
except FileNotFoundError:
    passed_transcript_ids = set()

problem = False
newly_passed_transcript_ids = set()
unknown_speaker_patterns = (
    re.compile(r"<cite(?:\s[^>]*)?>\s*unknown\s*</cite>", re.IGNORECASE),
    re.compile(
        r"(?:<!--block-->|<br\s*/?>\s*<br\s*/?>)\s*unknown\s*:\s*\d{1,2}:\d{2}",
        re.IGNORECASE,
    ),
)

for bid, post_name in sorted(buzzsprout_ids.items(), key=lambda item: item[0]):
    if not bid or bid in passed_transcript_ids:
        continue

    transcript_url = f"https://www.buzzsprout.com/1501960/{bid}/transcript"
    request = Request(transcript_url, headers={"User-Agent": "ADSP transcript checker"})
    try:
        with urlopen(request, timeout=15) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            transcript = response.read().decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError) as error:
        print(f"  {post_name}: could not check {transcript_url} ({error})")
        problem = True
        continue

    if any(pattern.search(transcript) for pattern in unknown_speaker_patterns):
        print(f"  {post_name}: unknown speaker in {transcript_url}")
        problem = True
    else:
        newly_passed_transcript_ids.add(bid)

if newly_passed_transcript_ids:
    passed_transcript_ids.update(newly_passed_transcript_ids)
    with open(transcript_cache_path, "w") as cache:
        for bid in sorted(passed_transcript_ids, key=int):
            cache.write(f"{bid}\n")

print(("❌" if problem else "✅") + " - No Unknown Speakers in Transcripts")

# Episodes
print("EPISODES CHECKS")

# Number, Title & Link in Episodes.md
problem_title = False
problem_date = False
problem_link_date = False
problem_link_num = False
episodes_rows = {}
episodes_row_pattern = re.compile(
    r"^\|\s*(?P<num>\d+)\s*\|\s*\[(?P<title>.*)\]"
    r"\(https://adspthepodcast\.com/"
    r"(?P<link_date>\d{4}/\d{2}/\d{2})/Episode-(?P<link_num>\d+)\.html\)"
    r"(?:\{:[^}]*\})?\s*\|\s*[^|]*\|\s*[^|]*\|"
    r"\s*(?P<release_date>\d{4}-\d{2}-\d{2})\s*\|"
)

with open("pages/episodes.md") as file:
    for line in file:
        match = episodes_row_pattern.match(line)
        if match:
            episodes_rows[int(match.group("num"))] = match.groupdict()

for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    num = int(post_name[:-3].split("-")[-1])
    date = post_name[:10]
    row = episodes_rows.get(num)

    if not row:
        problem_title = True
        problem_date = True
        problem_link_date = True
        problem_link_num = True
        continue

    if not row["title"].strip():
        problem_title = True
    if row["release_date"] != date:
        problem_date = True
    if row["link_date"].replace("/", "-") != date:
        problem_link_date = True
    if int(row["link_num"]) != num:
        problem_link_num = True

print(("❌" if problem_date else "✅") + " - Episode Date")
print(("❌" if problem_title else "✅") + " - Episode Title")
print(("❌" if problem_link_date else "✅") + " - Episode Date in Link")
print(("❌" if problem_link_num else "✅") + " - Episode Number in Link")

# Hoogle Translate by-algo-id Links Have Numeric q= Parameter
print("HOOGLE TRANSLATE CHECKS")
problem = False
invalid_links = []
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    with open("_posts/" + post_name) as post:
        for line_num, line in enumerate(post, 1):
            # Find all Hoogle Translate links in the line
            urls = re.findall(r"https://hoogletranslate\.com/[^\s\)]+", line)
            for url in urls:
                # Parse the URL and query parameters
                parsed = urlparse(url)
                params = parse_qs(parsed.query)

                # Check if type=by-algo-id
                if "type" in params and "by-algo-id" in params["type"]:
                    # Check if q parameter exists and is numeric
                    if "q" in params:
                        q_value = params["q"][0]
                        if not q_value.isdigit():
                            problem = True
                            invalid_links.append((post_name, line_num, url, q_value))
                    else:
                        problem = True
                        invalid_links.append((post_name, line_num, url, "MISSING"))

if invalid_links:
    print(f"❌ - Hoogle Translate by-algo-id Links Have Numeric q= Parameter")
    for post_name, line_num, url, q_value in invalid_links:
        print(f"  {post_name}:{line_num} - q={q_value} (should be numeric)")
else:
    print("✅ - Hoogle Translate by-algo-id Links Have Numeric q= Parameter")

# Hoogle Translate Link Format (Hoogle Translate first)
problem = False
fixed_files = []
pattern = re.compile(r"\[`([^`]+)` Hoogle Translate\]")
for post_name in os.listdir("_posts/"):
    if not post_name.endswith(".md"):
        continue
    file_path = "_posts/" + post_name
    with open(file_path) as post:
        content = post.read()

    # Find and fix any instances of "`algorithm` Hoogle Translate"
    matches = pattern.findall(content)
    if matches:
        new_content = content
        for algo in matches:
            old_pattern = f"[`{algo}` Hoogle Translate]"
            new_pattern = f"[Hoogle Translate `{algo}`]"
            new_content = new_content.replace(old_pattern, new_pattern)

        if new_content != content:
            with open(file_path, "w") as post:
                post.write(new_content)
            fixed_files.append((post_name, len(matches)))
            problem = True

if fixed_files:
    print(f"🔧 - Fixed Hoogle Translate Link Format (Hoogle Translate now first)")
    for post_name, count in fixed_files:
        print(f"  {post_name} - Fixed {count} link(s)")
else:
    print("✅ - Hoogle Translate Link Format (Hoogle Translate first)")
