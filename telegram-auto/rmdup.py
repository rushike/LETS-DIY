import asyncio
import sys
import os

async def rmdup(d):
  for dirname, dirs, files in os.walk(d):
    files_set = set(files)
    for filename in files:
      if " (1)" in filename:
        print(f"duplicate file name found : {filename}, path : {dirname}/{filename}")
        # os.remove(f"{dirname}/{filename}")
      

if __name__ == "__main__":
  """
  cmd args:
    1 -> folder path to remove duplicates
  """
  asyncio.run(rmdup(sys.argv[1]))
  # get_videos_files("/Users/rushike/dark/Child")