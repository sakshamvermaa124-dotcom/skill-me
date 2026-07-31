import os

domain_topics = {
    "web-dev": ["HTML/CSS Basics", "JavaScript DOM", "Responsive Design", "API Integration"],
    "python": ["Syntax & Data Structures", "OOP & Modules", "File Handling & APIs", "Web Scraping/Flask Basic"],
    "react": ["Components & Props", "State & Hooks", "Routing & Context API", "State Management (Redux/Zustand)"],
    "node": ["Express Basics & Routing", "MongoDB & Mongoose", "Authentication (JWT)", "WebSockets/Deployment"],
    "java": ["Core Java OOP", "Spring Boot Basics", "JPA & Hibernate", "REST APIs & Security"],
    "ml": ["Data Preprocessing", "Supervised Learning", "Unsupervised Learning", "Model Deployment"],
    "datascience": ["Pandas & NumPy", "Data Visualization", "Statistical Analysis", "Machine Learning Basics"],
    "flutter": ["Dart Basics & UI", "State Management", "Navigation & API", "Firebase Integration"],
    "devops": ["Linux & Shell Scripting", "Docker & Containers", "CI/CD (GitHub Actions)", "Terraform/Kubernetes"],
    "cpp": ["Pointers & Memory", "OOP Concepts", "STL (Vectors, Maps)", "Advanced DSA Applications"],
    "cloud": ["Cloud Basics & IAM", "Compute & Storage", "Networking & Databases", "Serverless & Deployment"],
    "cyber": ["Network Fundamentals", "Vulnerability Scanning", "Web App Security", "Incident Response"]
}

base_dir = "SkillMe-Intern-Tasks"

def generate_tasks():
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    for domain, topics in domain_topics.items():
        domain_dir = os.path.join(base_dir, domain)
        if not os.path.exists(domain_dir):
            os.makedirs(domain_dir)
            
        for week in range(1, 5):
            week_dir = os.path.join(domain_dir, f"week-{week}")
            if not os.path.exists(week_dir):
                os.makedirs(week_dir)
                
            topic = topics[week - 1]
            
            # Task 1
            task1 = f"""---
title: "Week {week} Task 1: Research & Setup for {topic}"
difficulty: "easy"
labels: ["week-{week}", "easy", "{domain}"]
---
## Objective
Understand the fundamentals of **{topic}** and set up your local environment for this week's assignments in the **{domain}** track.

## Requirements
1. Research **{topic}** and write a brief summary in your `PROGRESS.md` file.
2. Set up any necessary tools, libraries, or frameworks required.
3. Create a new branch `feature/week-{week}-setup`.
4. Commit your findings and push the branch.
"""
            with open(os.path.join(week_dir, "01-setup.md"), "w", encoding="utf-8") as f:
                f.write(task1)
                
            # Task 2
            task2 = f"""---
title: "Week {week} Task 2: Implement {topic}"
difficulty: "medium"
labels: ["week-{week}", "medium", "{domain}"]
---
## Objective
Apply your knowledge of **{topic}** to implement the core feature for this week in the **{domain}** track.

## Requirements
1. Write clean, modular code demonstrating your understanding of **{topic}**.
2. Follow best practices for the {domain} ecosystem.
3. Ensure the code handles edge cases effectively.
4. Commit your changes to the `feature/week-{week}-setup` branch.
"""
            with open(os.path.join(week_dir, "02-core-feature.md"), "w", encoding="utf-8") as f:
                f.write(task2)
                
            # Task 3
            task3 = f"""---
title: "Week {week} Task 3: Testing & Code Review for {topic}"
difficulty: "medium"
labels: ["week-{week}", "medium", "{domain}"]
---
## Objective
Validate your implementation of **{topic}** and prepare your code for review.

## Requirements
1. Write tests or perform manual verification of your code.
2. Review your own code against industry standards.
3. Push your final changes and open a Pull Request linking to this issue.
4. Request a review from the mentor/admin team.
"""
            with open(os.path.join(week_dir, "03-testing.md"), "w", encoding="utf-8") as f:
                f.write(task3)

    print(f"Generated tasks for all domains in '{base_dir}' directory.")
    
if __name__ == "__main__":
    generate_tasks()
