#!/usr/bin/env python3
"""
Script to update episode posts with proper Thrust and CUDA tags:
1. Any post with a Thrust tag should also have a CUDA tag
2. Any post mentioning thrust:: should have both Thrust and CUDA tags
Preserves the bracket format for tags.
"""

import re
from pathlib import Path


def parse_tags_line(line):
    """Parse a tags line and return the list of tags."""
    # Handle format: tags: [tag1, tag2, tag3]
    match = re.search(r'tags:\s*\[(.*?)\]', line)
    if match:
        tags_str = match.group(1)
        if tags_str.strip():
            # Split by comma and clean up
            tags = [tag.strip().strip('"\'') for tag in tags_str.split(',')]
            return [tag for tag in tags if tag]  # Remove empty strings
        else:
            return []
    return None


def format_tags_line(tags):
    """Format tags back into the bracket format."""
    if not tags:
        return "tags: []"

    # Join tags with proper formatting
    tags_str = ', '.join(tags)
    return f"tags: [{tags_str}]"


def update_post_tags(file_path):
    """Update tags for a single post file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find frontmatter boundaries
    frontmatter_start = -1
    frontmatter_end = -1
    tags_line_idx = -1

    for i, line in enumerate(lines):
        if line.strip() == '---':
            if frontmatter_start == -1:
                frontmatter_start = i
            else:
                frontmatter_end = i
                break
        elif frontmatter_start != -1 and line.strip().startswith('tags:'):
            tags_line_idx = i

    if frontmatter_start == -1 or frontmatter_end == -1:
        print(f"⚠️  Could not find frontmatter in {file_path.name}")
        return False

    # Check if post mentions thrust::
    body = ''.join(lines[frontmatter_end + 1:])
    mentions_thrust_namespace = 'thrust::' in body

    # Parse current tags
    current_tags = []
    if tags_line_idx != -1:
        current_tags = parse_tags_line(lines[tags_line_idx])
        if current_tags is None:
            print(f"⚠️  Could not parse tags in {file_path.name}")
            return False

    has_thrust_tag = 'Thrust' in current_tags
    has_cuda_tag = 'CUDA' in current_tags

    updated = False

    # Rule 1: If post mentions thrust:: namespace, it should have both Thrust and CUDA tags
    if mentions_thrust_namespace:
        if not has_thrust_tag:
            current_tags.append('Thrust')
            updated = True
            print(f"  ➕ Added 'Thrust' tag (mentions thrust::)")

        if not has_cuda_tag:
            current_tags.append('CUDA')
            updated = True
            print(f"  ➕ Added 'CUDA' tag (mentions thrust::)")

    # Rule 2: If post has Thrust tag, it should also have CUDA tag
    elif has_thrust_tag and not has_cuda_tag:
        current_tags.append('CUDA')
        updated = True
        print(f"  ➕ Added 'CUDA' tag (has Thrust tag)")

    if updated:
        # Update the tags line
        if tags_line_idx != -1:
            lines[tags_line_idx] = format_tags_line(current_tags) + '\n'
        else:
            # Insert tags line after title (typically line 2)
            title_line_idx = -1
            for i in range(frontmatter_start + 1, frontmatter_end):
                if lines[i].strip().startswith('title:'):
                    title_line_idx = i
                    break

            if title_line_idx != -1:
                lines.insert(title_line_idx + 1,
                             format_tags_line(current_tags) + '\n')
            else:
                # Fallback: insert after frontmatter start
                lines.insert(frontmatter_start + 1,
                             format_tags_line(current_tags) + '\n')

        # Write back to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return True

    return False


def main():
    """Main function to update all posts."""
    posts_dir = Path('_posts')
    updated_count = 0

    print("🔍 Analyzing all episode posts for Thrust/CUDA tag updates...")

    for post_file in sorted(posts_dir.glob('*.md')):
        try:
            print(f"\n📄 Checking {post_file.name}...")

            if update_post_tags(post_file):
                updated_count += 1
                print(f"  ✅ Updated {post_file.name}")
            else:
                print(f"  ⏭️  No changes needed")

        except Exception as e:
            print(f"  ❌ Error processing {post_file.name}: {e}")

    print(f"\n🎉 Completed! Updated {updated_count} posts.")

    if updated_count > 0:
        print(
            "\n💡 Now you can run 'python3 reorder_logos.py' to see the updated frequencies!"
        )


if __name__ == '__main__':
    main()
