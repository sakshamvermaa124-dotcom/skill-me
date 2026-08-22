import asyncio, sys
sys.path.append('backend')
from services.task_service import TaskService
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    ts = TaskService()
    for week in range(1, 5):
        tasks = await ts.fetch_tasks('python', week)
        print(f"Week {week} tasks: {len(tasks)}")
        for i, t in enumerate(tasks):
            print(f"  Task {i+1}: {t['title']}")

asyncio.run(main())
