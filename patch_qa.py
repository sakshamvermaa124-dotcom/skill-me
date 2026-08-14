import re

def patch_qa():
    with open("style.css", "r", encoding="utf-8") as f:
        css = f.read()

    # Fix 1: Change 100vh to 100dvh in .nav-links and add safe areas
    nav_links_pattern = r"(\.nav-links\s*\{[^}]*?height:\s*)100vh([^}]*?padding:\s*[^;]+;)([^}]*?\})"
    
    # We want to replace 100vh with 100dvh, add overflow-y, and update padding to include safe areas
    def nav_links_repl(match):
        height_part = match.group(1) + "100dvh"
        middle_part = match.group(2)
        end_part = match.group(3)
        
        # Add overflow and safe areas
        new_rules = """
    overflow-y: auto;
    padding-top: max(80px, env(safe-area-inset-top));
    padding-bottom: max(24px, env(safe-area-inset-bottom));
    padding-left: max(24px, env(safe-area-inset-left));
    padding-right: max(24px, env(safe-area-inset-right));"""
        
        # Remove the old padding from middle_part
        middle_part = re.sub(r"padding:\s*[^;]+;", "", middle_part)
        
        return height_part + middle_part + new_rules + end_part

    if "100dvh" not in css:
        css = re.sub(nav_links_pattern, nav_links_repl, css)

    # Fix 2: Add overscroll-behavior to body
    if "overscroll-behavior-x" not in css:
        body_pattern = r"(body\s*\{)"
        css = re.sub(body_pattern, r"\1\n  overscroll-behavior-x: none;", css)

    with open("style.css", "w", encoding="utf-8") as f:
        f.write(css)
    print("QA fixes applied.")

if __name__ == '__main__':
    patch_qa()
