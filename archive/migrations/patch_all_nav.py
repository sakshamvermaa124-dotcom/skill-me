
import os

files_to_patch = ["apply.html", "contact.html", "privacy.html", "refunds.html", "terms.html"]

for file in files_to_patch:
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Patch HTML
    content = content.replace(
        `<div class="nav-links-center" id="nav-links-center">`,
        `<div class="nav-links-center" id="nav-links-center" data-lenis-prevent>`
    )
    
    # Patch JS for apply.html
    if file == "apply.html":
        old_js = """    if (navToggle && navLinks) {
      navToggle.addEventListener('click', () => {
        navToggle.classList.toggle('active');
        navLinks.classList.toggle('open');
      });"""
        new_js = """    if (navToggle && navLinks) {
      navToggle.addEventListener('click', () => {
        const isOpen = navLinks.classList.toggle('open');
        navToggle.classList.toggle('active', isOpen);
        document.body.style.overflow = isOpen ? 'hidden' : '';
        document.documentElement.style.overflow = isOpen ? 'hidden' : '';
      });"""
        content = content.replace(old_js, new_js)
    else:
        old_js = """    t.addEventListener('click', function() {
      t.classList.toggle('active');
      n.classList.toggle('open');
    });"""
        new_js = """    t.addEventListener('click', function() {
      var isOpen = n.classList.toggle('open');
      t.classList.toggle('active', isOpen);
      document.body.style.overflow = isOpen ? 'hidden' : '';
      document.documentElement.style.overflow = isOpen ? 'hidden' : '';
    });"""
        content = content.replace(old_js, new_js)

    with open(file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Patched {file}")

