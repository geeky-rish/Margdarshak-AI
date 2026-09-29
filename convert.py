import html
import re

txt_path = r'C:\Users\DELL\Margdarshak-AI\happy_path_test_plan.txt'
html_path = r'C:\Users\DELL\Margdarshak-AI\happy_path_test_plan.html'

with open(txt_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Basic markdown-like replacements
html_content = html.escape(text)
html_content = re.sub(r'======+.*?======+', '', html_content) # Remove ==== lines
html_content = re.sub(r'(?m)^### (.*?)$', r'<h3>\1</h3>', html_content)
html_content = re.sub(r'(?m)^## (.*?)$', r'<h2>\1</h2>', html_content)
html_content = re.sub(r'(?m)^# (.*?)$', r'<h1>\1</h1>', html_content)
html_content = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_content)

# Handle code blocks
parts = html_content.split('`')
for i in range(1, len(parts), 2):
    parts[i] = f'<pre>{parts[i].replace("json\n", "")}</pre>'
html_content = ''.join(parts)

# Replace newlines with <br> outside of <pre> tags
final_parts = html_content.split('<pre>')
for i in range(len(final_parts)):
    sub_parts = final_parts[i].split('</pre>')
    sub_parts[0] = sub_parts[0].replace('\n', '<br>')
    final_parts[i] = '</pre>'.join(sub_parts)
html_content = '<pre>'.join(final_parts)

template = f'''<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; line-height: 1.5; margin: 40px; color: #333; }}
  h1, h2, h3 {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 30px; }}
  pre {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border: 1px solid #ddd; white-space: pre-wrap; font-family: Consolas, monospace; }}
  b {{ color: #000; }}
</style>
</head>
<body>
<h2>Margdarshak-AI: Positive Test Plan</h2>
{html_content}
</body>
</html>'''

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(template)
print('HTML generated')
