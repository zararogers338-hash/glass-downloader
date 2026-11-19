"""Cancellation-safe lifetime for a process owned by a single transfer."""
import asyncio
import os
import signal
from contextlib import asynccontextmanager


async def stop_process(proc, tree):
    if proc.returncode is None:
        try:
            if tree and os.name=="nt":
                killer=await asyncio.create_subprocess_exec("taskkill","/PID",str(proc.pid),"/T","/F",
                    creationflags=0x08000000,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
                await killer.wait()
                if proc.returncode is None:proc.kill()
            elif tree:
                os.killpg(proc.pid,signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            pass
    # Drain pipes even if the child exited while its reader was being cancelled.
    await proc.communicate()


@asynccontextmanager
async def owned_process(args, *, cwd=None, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, tree=False, direct=False):
    env={k:v for k,v in os.environ.items() if not k.lower().endswith("_proxy")}
    if direct:env["NO_PROXY"]="*"
    flags={"creationflags":0x08000000} if os.name=="nt" else {"start_new_session":tree}
    spawning=asyncio.create_task(asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.DEVNULL,
        stdout=stdout,stderr=stderr,cwd=cwd,env=env,**flags))
    try:
        proc=await asyncio.shield(spawning)
    except asyncio.CancelledError:
        proc=await spawning
        await stop_process(proc,tree)
        raise
    try:
        yield proc
    finally:
        await stop_process(proc,tree)

