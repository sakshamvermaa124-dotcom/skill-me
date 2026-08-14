import re
import glob

def restructure_nav():
    html_files = glob.glob("*.html")
    for file in html_files:
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()

        # Find the entire nav block
        nav_pattern = re.compile(r'(<nav class="navbar"[^>]*>.*?<div class="container">)(.*?)(</nav>)', re.DOTALL)
        match = nav_pattern.search(content)
        if not match:
            continue
            
        nav_start = match.group(1)
        nav_inner = match.group(2)
        nav_end = match.group(3)
        
        if "nav-links-center" in nav_inner:
            continue # Already processed
            
        # Extract Logo
        logo_match = re.search(r'(<a[^>]*class="nav-logo"[^>]*>.*?</a>)', nav_inner, re.DOTALL)
        logo_html = logo_match.group(1) if logo_match else ""
        
        # Extract nav-links
        nav_links_match = re.search(r'<div class="nav-links"[^>]*>(.*?)</div>', nav_inner, re.DOTALL)
        nav_links_inner = nav_links_match.group(1) if nav_links_match else ""
        
        # Parse links
        links = re.findall(r'<a\s+[^>]*>.*?</a>', nav_links_inner, re.DOTALL)
        center_links = []
        right_links = []
        for link in links:
            if 'class="nav-cta"' in link or 'class="nav-link-dashboard"' in link:
                right_links.append(link)
            else:
                center_links.append(link)
                
        # Extract Toggle Button
        btn_match = re.search(r'(<button class="nav-toggle"[^>]*>.*?</button>)', nav_inner, re.DOTALL)
        btn_html = btn_match.group(1) if btn_match else ""
        
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
        
        # Add the closing </div> for container which was eaten by the match?
        # Wait, nav_inner is EVERYTHING inside <div class="container"> up to </nav>
        # So we need to ensure the closing </div> is kept.
        # nav_pattern caught (.*?)(</nav>), which includes the closing </div> of .container.
        new_nav_inner += "</div>\n  "
        
        new_content = content[:match.start()] + nav_start + new_nav_inner + nav_end + content[match.end():]
        
        with open(file, "w", encoding="utf-8") as fw:
            fw.write(new_content)
        print(f"Processed {file}")

if __name__ == '__main__':
    restructure_nav()
