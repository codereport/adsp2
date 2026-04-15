#!/usr/bin/env python3
"""
Script to automatically reorder programming language logos in _layouts/home.html
based on the frequency of tags in episode posts.
"""

import os
import re
import yaml
from collections import Counter
from pathlib import Path

# Define the technologies we track with their logo configurations
TECHNOLOGIES = {
    'C++': {
        'tag': 'C%2B%2B',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/cpp.png',
        'height': '80px',
        'width': '95px',
        'extra_attrs': ''
    },
    'Rust': {
        'tag':
        'Rust',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/rust.png',
        'height':
        '80px',
        'width':
        '100px',
        'extra_attrs':
        '''id="rust-logo"
                        data-light-src="https://raw.githubusercontent.com/codereport/logos/main/rust.png"
                        data-dark-src="https://raw.githubusercontent.com/codereport/logos/main/rust_darkmode.png"'''
    },
    'APL': {
        'tag': 'APL',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/apl.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'Swift': {
        'tag': 'Swift',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/swift.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'Haskell': {
        'tag': 'Haskell',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/haskell.svg',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'Thrust': {
        'tag': 'Thrust',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/thrust.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'Python': {
        'tag': 'Python',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/python.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'BQN': {
        'tag': 'BQN',
        'img_src': 'https://raw.githubusercontent.com/codereport/logos/main/bqn.svg',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'Fortran': {
        'tag': 'Fortran',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/fortran.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'CUDA': {
        'tag': 'CUDA',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/cuda.png',
        'height': '80px',
        'width': '140px',
        'extra_attrs': ''
    },
    'Clojure': {
        'tag': 'Clojure',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/clojure.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'Erlang': {
        'tag': 'Erlang',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/erlang.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    },
    'D': {
        'tag': 'D',
        'img_src':
        'https://raw.githubusercontent.com/codereport/logos/main/d.png',
        'height': '80px',
        'width': '100px',
        'extra_attrs': ''
    }
}


def count_tags_in_posts():
    """Count frequency of each technology tag in all episode posts."""
    tag_counts = Counter()
    posts_dir = Path('_posts')

    for post_file in posts_dir.glob('*.md'):
        try:
            with open(post_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    # Parse YAML frontmatter
                    metadata = yaml.safe_load(frontmatter)

                    if 'tags' in metadata and metadata['tags']:
                        tags = metadata['tags']
                        if isinstance(tags, list):
                            for tag in tags:
                                if tag in TECHNOLOGIES:
                                    tag_counts[tag] += 1

        except Exception as e:
            print(f"Error processing {post_file}: {e}")
            continue

    return tag_counts


def generate_logo_html(tech_name, config):
    """Generate HTML for a single logo."""
    extra_attrs = f'\n                        {config["extra_attrs"]}' if config[
        'extra_attrs'] else ''

    return f'''            <div style="float: left;">
                <a href="https://adspthepodcast.com/tags/#{config['tag']}">
                    <img {f'{config["extra_attrs"]} ' if config['extra_attrs'] else ''}src="{config['img_src']}"
                        height={config['height']} width={config['width']}>
                </a>
            </div>'''


def update_home_html(ordered_technologies):
    """Update the _layouts/home.html file with reordered logos."""
    home_file = Path('_layouts/home.html')

    with open(home_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Generate new logos section
    logos_html = []
    for tech in ordered_technologies:
        if tech in TECHNOLOGIES:
            logos_html.append(generate_logo_html(tech, TECHNOLOGIES[tech]))

    new_logos_section = '\n'.join(logos_html)

    # Find and replace the logos section
    # Look for the pattern between "Episodes about (or mentioning):" and the next h3
    pattern = r'(\s*<h3>Episodes about \(or mentioning\):</h3>\s*<div style="display: inline-block; margin-left: auto;  margin-right: auto">)(.*?)(\s*</div>\s*<h3>Most Recent Episodes:</h3>)'

    replacement = f'\\1\n{new_logos_section}\n        \\3'

    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    if new_content != content:
        with open(home_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("✅ Updated _layouts/home.html with reordered logos")
        return True
    else:
        print("⚠️  No changes made to _layouts/home.html")
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
    ordered_techs = sorted(tag_counts.keys(),
                           key=lambda x: tag_counts[x],
                           reverse=True)

    # Add any technologies that weren't found in posts (with 0 count) at the end
    missing_techs = [
        tech for tech in TECHNOLOGIES.keys() if tech not in tag_counts
    ]
    ordered_techs.extend(sorted(missing_techs))

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
        print("\n❌ Failed to update the HTML file.")


if __name__ == '__main__':
    main()
