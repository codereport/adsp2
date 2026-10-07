#!/usr/bin/env python3
"""
Script to automatically reorder topic logos in _layouts/home.html
based on the frequency of tags in episode posts.
"""

import re
from collections import Counter

from generate_episodes import POSTS_DIR, ROOT, post_tag_values

# Define the technologies we track with their logo configurations
TECHNOLOGIES = {
    'codex': {
        'tag': 'codex',
        'display_name': 'Codex',
        'img_src': "{{ '/assets/img/codex.svg' | relative_url }}",
        'extra_attrs': ''
    },
    'claude': {
        'tag': 'claude',
        'display_name': 'Claude',
        'img_src': "{{ '/assets/img/claude.svg' | relative_url }}",
        'extra_attrs': ''
    },
    'cursor': {
        'tag': 'cursor',
        'display_name': 'Cursor',
        'img_src': "{{ '/assets/img/cursor.svg' | relative_url }}",
        'extra_attrs': 'class="topic-logo-invert"'
    },
    'C++': {
        'tag': 'C%2B%2B',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/cpp.png',
        'extra_attrs': ''
    },
    'Rust': {
        'tag':
        'Rust',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/rust.png',
        'extra_attrs':
        '''id="rust-logo"
                        data-light-src="https://raw.githubusercontent.com/codereport/logos/main/rust.png"
                        data-dark-src="https://raw.githubusercontent.com/codereport/logos/main/rust_darkmode.png"'''
    },
    'APL': {
        'tag': 'APL',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/apl.png',
        'extra_attrs': ''
    },
    'Swift': {
        'tag': 'Swift',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/swift.png',
        'extra_attrs': ''
    },
    'Haskell': {
        'tag': 'Haskell',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/haskell.svg',
        'extra_attrs': ''
    },
    'Thrust': {
        'tag': 'Thrust',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/thrust.png',
        'extra_attrs': ''
    },
    'Python': {
        'tag': 'Python',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/python.png',
        'extra_attrs': ''
    },
    'BQN': {
        'tag': 'BQN',
        'img_src': 'https://raw.githubusercontent.com/codereport/logos/main/bqn.svg',
        'extra_attrs': ''
    },
    'Fortran': {
        'tag': 'Fortran',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/fortran.png',
        'extra_attrs': ''
    },
    'CUDA': {
        'tag': 'CUDA',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/cuda.png',
        'extra_attrs': ''
    },
    'Clojure': {
        'tag': 'Clojure',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/clojure.png',
        'extra_attrs': ''
    },
    'Erlang': {
        'tag': 'Erlang',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/erlang.png',
        'extra_attrs': ''
    },
    'D': {
        'tag': 'D',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/d.png',
        'extra_attrs': ''
    }
}


def count_tags_in_posts():
    """Count frequency of each technology tag in all episode posts."""
    tag_counts = Counter()
    posts_dir = POSTS_DIR

    for post_file in posts_dir.glob('*.md'):
        try:
            with open(post_file, 'r', encoding='utf-8') as f:
                content = f.read()

            for tag in set(post_tag_values(content)):
                if tag in TECHNOLOGIES:
                    tag_counts[tag] += 1

        except Exception as e:
            print(f"Error processing {post_file}: {e}")
            continue

    return tag_counts


def generate_logo_html(tech_name, config):
    """Generate HTML for a single logo."""
    extra_attrs = f'{config["extra_attrs"]}\n                    ' if config[
        'extra_attrs'] else ''

    display_name = config.get('display_name', tech_name)
    return f'''            <a class="topic-logo" href="{{{{ '/tags/' | relative_url }}}}#{config['tag']}">
                <img {extra_attrs}src="{config['img_src']}" alt="{display_name}">
            </a>'''


def update_home_html(ordered_technologies):
    """Update the _layouts/home.html file with reordered logos."""
    home_file = ROOT / '_layouts' / 'home.html'

    with open(home_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Generate new logos section
    logos_html = []
    for tech in ordered_technologies:
        if tech in TECHNOLOGIES:
            logos_html.append(generate_logo_html(tech, TECHNOLOGIES[tech]))

    new_logos_section = '\n'.join(logos_html)

    # Find and replace the logos section
    # Look for the pattern between the topic heading and company section.
    pattern = r'(\s*<h3>Episodes about \(or mentioning\):</h3>\s*<div class="topic-logos">)(.*?)(\s*</div>\s*<h3>Interviews with Industry Experts from:</h3>)'

    new_content, replacements = re.subn(
        pattern, lambda match: match.group(1) + '\n' + new_logos_section + match.group(3),
        content, flags=re.DOTALL,
    )
    if replacements != 1:
        raise ValueError("could not find the homepage topic logos section")

    if new_content != content:
        with open(home_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("✅ Updated _layouts/home.html with reordered logos")
        return True
    else:
        print("✅ Homepage topic logos are up to date")
        return False


def main():
    """Main function to reorder logos based on tag frequency."""
    print("🔍 Analyzing episode tags...")

    # Count tags
    tag_counts = count_tags_in_posts()

    if not tag_counts:
        print("❌ No tags found in posts")
        return

    # Sort technologies by frequency (descending)
    ordered_techs = sorted(TECHNOLOGIES,
                           key=lambda tech: (-tag_counts[tech], tech.casefold()))

    print("\n📊 Tag frequencies:")
    for tech in ordered_techs:
        count = tag_counts.get(tech, 0)
        print(f"  {tech}: {count} episodes")

    # Update the HTML file
    print(f"\n🔄 Reordering logos...")
    success = update_home_html(ordered_techs)

    if success:
        print("\n🎉 Logo reordering complete!")
        print(
            "The logos are now ordered from most frequent to least frequent.")
    else:
        print("\n✅ Logo order is already current.")


if __name__ == '__main__':
    main()
