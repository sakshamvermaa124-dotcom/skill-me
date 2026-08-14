import re
import glob

def patch():
    html_files = glob.glob("*.html")
    for file in html_files:
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
            
        if "nav-links-center" in content:
            print(f"Skipping {file} (already processed)")
            continue

        nav_pattern = re.compile(r'(<nav [^>]*>.*?<div class="container">)(.*?)(</nav>)', re.DOTALL)
        match = nav_pattern.search(content)
        if not match:
            print(f"No nav block found in {file}")
            continue
            
        nav_start = match.group(1)
        nav_inner = match.group(2)
        nav_end = match.group(3)

        logo_match = re.search(r'(<a[^>]*class="nav-logo"[^>]*>.*?</a>)', nav_inner, re.DOTALL)
        logo_html = logo_match.group(1) if logo_match else ""

        nav_links_match = re.search(r'<div class="nav-links"[^>]*>(.*?)</div>', nav_inner, re.DOTALL)
        nav_links_inner = nav_links_match.group(1) if nav_links_match else ""

        # Find all a and button tags in nav_links_inner
        elements = re.findall(r'<a\s+[^>]*>.*?</a>|<button\s+[^>]*>.*?</button>', nav_links_inner, re.DOTALL)
        center_links = []
        right_links = []
        for el in elements:
            if 'class="nav-cta"' in el or 'class="nav-link-dashboard"' in el or 'signOut()' in el or 'nav-cta' in el or 'Dashboard' in el or 'Log Out' in el:
                right_links.append(el)
            else:
                center_links.append(el)

        btn_match = re.search(r'(<button class="nav-toggle"[^>]*>.*?</button>)', nav_inner, re.DOTALL)
        btn_html = btn_match.group(1) if btn_match else ""
        
        # If btn_html is empty, let's inject a default one just in case
        if not btn_html:
            btn_html = """<button class="nav-toggle" id="nav-toggle" aria-label="Toggle navigation menu">
        <span></span>
        <span></span>
        <span></span>
      </button>"""

        new_nav_inner = f"""
    <div class="nav-left">
      {logo_html}
    </div>
    <div class="nav-links-center" id="nav-links-center">
      {"\n      ".join(center_links)}
    </div>
    <div class="nav-actions-right">
      {"\n      ".join(right_links)}
      {btn_html}
    </div>
  """
        new_nav_inner += "</div>\n  "
        
        new_content = content[:match.start()] + nav_start + new_nav_inner + nav_end + content[match.end():]
        
        with open(file, "w", encoding="utf-8") as fw:
            fw.write(new_content)
        print(f"Processed {file}")

if __name__ == "__main__":
    patch()
