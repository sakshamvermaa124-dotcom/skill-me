import re

with open('plan.md', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'Needs the new "Build Your Internship Proof 🚀" section with 3 cards.',
    'Needs the 3 new Flex feature cards (Task PDF, Portfolio, Instant Certificate) integrated seamlessly and directly into the dashboard layout without a wrapper section.'
)

content = content.replace(
    'render the "Build Your Internship Proof 🚀" section',
    'render the three new Flex Option cards directly into the dashboard layout'
)

with open('plan.md', 'w', encoding='utf-8') as f:
    f.write(content)
