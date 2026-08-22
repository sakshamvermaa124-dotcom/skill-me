import re
import glob

def patch_css():
    with open("style.css", "r", encoding="utf-8") as f:
        css = f.read()

    # Fix 1: Word wrap on terminal-body
    if "word-break: break-word" not in css:
        term_body = r"(\.terminal-body\s*\{[^}]*)(\})"
        css = re.sub(term_body, r"\1  word-break: break-word;\n  white-space: pre-wrap;\n  overflow-wrap: break-word;\n\2", css)

    # Fix 2: Touch targets
    if "min-height: 48px" not in css:
        mobile_480 = r"(@media\s*\(max-width:\s*480px\)\s*\{)"
        fixes_480 = r"\1\n  .btn-primary, .btn-secondary, .nav-cta { min-height: 48px; display: inline-flex; align-items: center; justify-content: center; }\n"
        css = re.sub(mobile_480, fixes_480, css, count=1)
        
    # Fix 3: Hero stats on ultra-mobile
    if "max-width: 350px" not in css:
        mobile_350 = "\n@media (max-width: 350px) {\n  .hero-stats { grid-template-columns: 1fr !important; }\n}\n"
        css += mobile_350

    # Fix 4: Force 16px input font size
    if "font-size: 16px !important" not in css:
        mobile_768 = r"(@media\s*\(max-width:\s*768px\)\s*\{)"
        fixes_768 = r"\1\n  input, select, textarea { font-size: 16px !important; }\n"
        css = re.sub(mobile_768, fixes_768, css, count=1)

    with open("style.css", "w", encoding="utf-8") as f:
        f.write(css)
    print("CSS patched.")

def patch_html():
    nav_button = """
      <button class="nav-toggle" id="nav-toggle" aria-label="Toggle navigation menu">
        <span></span>
        <span></span>
        <span></span>
      </button>"""
      
    html_files = glob.glob("*.html")
    for file in html_files:
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
            
        if 'id="nav-toggle"' not in content:
            # We want to insert it right before the </div> closing the nav .container
            # Example:
            #       <a href="dashboard.html"...>...</a>
            #     </div>
            #   </nav>
            # Pattern: matches the end of the .nav-links div, and inserts before the </div> of the container.
            
            pattern = re.compile(r'(<div class="nav-links" id="nav-links">.*?</nav>)', re.DOTALL)
            match = pattern.search(content)
            if match:
                # find the last </div> before </nav>
                nav_block = match.group(1)
                last_div_idx = nav_block.rfind("</div>")
                
                if last_div_idx != -1:
                    new_nav = nav_block[:last_div_idx] + nav_button + "\n    " + nav_block[last_div_idx:]
                    content = content[:match.start()] + new_nav + content[match.end():]
                    
                    with open(file, "w", encoding="utf-8") as fw:
                        fw.write(content)
                    print(f"Patched {file}")
                else:
                    print(f"Failed to find closing container div in {file}")
            else:
                print(f"No nav-links found in {file}")
        else:
            print(f"Already patched {file}")

if __name__ == '__main__':
    patch_css()
    patch_html()
