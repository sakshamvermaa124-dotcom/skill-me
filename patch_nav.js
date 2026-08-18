const fs = require('fs');
const files = ['apply.html', 'contact.html', 'privacy.html', 'refunds.html', 'terms.html'];

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf8');
  
  // HTML patch
  content = content.replace(
    '<div class="nav-links-center" id="nav-links-center">',
    '<div class="nav-links-center" id="nav-links-center" data-lenis-prevent>'
  );

  // JS patch
  if (file === 'apply.html') {
    content = content.replace(
      /navToggle\.classList\.toggle\('active'\);\s*navLinks\.classList\.toggle\('open'\);/g,
      `const isOpen = navLinks.classList.toggle('open');
        navToggle.classList.toggle('active', isOpen);
        document.body.style.overflow = isOpen ? 'hidden' : '';
        document.documentElement.style.overflow = isOpen ? 'hidden' : '';`
    );
  } else {
    content = content.replace(
      /t\.classList\.toggle\('active'\);\s*n\.classList\.toggle\('open'\);/g,
      `var isOpen = n.classList.toggle('open');
      t.classList.toggle('active', isOpen);
      document.body.style.overflow = isOpen ? 'hidden' : '';
      document.documentElement.style.overflow = isOpen ? 'hidden' : '';`
    );
  }
  
  fs.writeFileSync(file, content);
  console.log('Patched ' + file);
});
