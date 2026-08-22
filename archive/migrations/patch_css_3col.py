import re

def patch_css():
    with open("style.css", "r", encoding="utf-8") as f:
        css = f.read()
        
    # Replace the existing .navbar .container flex with grid
    # Wait, currently it's just: .navbar .container { display: flex; align-items: center; justify-content: space-between; max-width: 100% !important; padding-left: 12px !important; padding-right: 12px !important; }
    # I'll append the new desktop 3-col rules at the bottom of the NAVBAR section.
    
    desktop_3col = """
/* Desktop 3-Column Split Nav */
@media (min-width: 769px) {
  .navbar .container {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    width: 100%;
  }
  .nav-left { justify-self: start; }
  .nav-links-center {
    display: flex;
    gap: 32px;
    justify-self: center;
    align-items: center;
  }
  .nav-actions-right {
    display: flex;
    gap: 16px;
    justify-self: end;
    align-items: center;
  }
  .nav-links-center a {
    color: var(--text-secondary);
    font-size: 0.94rem;
    font-weight: 500;
    transition: color 0.2s ease;
  }
  .nav-links-center a:hover,
  .nav-links-center a.active {
    color: var(--text-primary);
  }
  .nav-toggle { display: none; }
}

/* Mobile Split Nav Adjustments */
@media (max-width: 768px) {
  .navbar .container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
  }
  
  .nav-links-center {
    display: none; /* hidden by default */
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100dvh;
    background: rgba(11, 11, 14, 0.97);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 28px;
    z-index: 999;
    text-align: center;
    overflow-y: auto;
    padding-top: max(80px, env(safe-area-inset-top));
    padding-bottom: max(24px, env(safe-area-inset-bottom));
    padding-left: max(24px, env(safe-area-inset-left));
    padding-right: max(24px, env(safe-area-inset-right));
  }
  
  .nav-links-center.open {
    display: flex;
  }
  
  .nav-links-center a {
    font-size: 1.3rem;
    color: var(--text-primary);
    padding: 8px 0;
  }
  
  .nav-actions-right {
    display: flex;
    align-items: center;
    gap: 12px;
    z-index: 1001;
  }
}
"""

    if "grid-template-columns: 1fr auto 1fr" not in css:
        css += desktop_3col
        
    with open("style.css", "w", encoding="utf-8") as f:
        f.write(css)

if __name__ == "__main__":
    patch_css()
