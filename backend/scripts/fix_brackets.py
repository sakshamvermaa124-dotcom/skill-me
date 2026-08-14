import codecs

def fix():
    with codecs.open('dashboard.js', 'r', 'utf-8') as f:
        code = f.read()

    # Fix 1: Add else if
    target1 = """          }
        certSection.style.display = 'block';
        certSection.innerHTML = `
          <div class="cert-progress-hint">"""
    
    replace1 = """          }
        } else if (pct > 0) {
          certSection.style.display = 'block';
          certSection.innerHTML = `
            <div class="cert-progress-hint">"""
    
    code = code.replace(target1, replace1)

    # Fix 2: Close brackets for setTimeout
    target2 = """          </div>`;
      }
    }


    // Submissions"""
    
    replace2 = """          </div>`;
        }
      }
    });

    // Submissions"""
    
    code = code.replace(target2, replace2)

    with codecs.open('dashboard.js', 'w', 'utf-8') as f:
        f.write(code)

if __name__ == "__main__":
    fix()
