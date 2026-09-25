"""Own Windows worker trees so cancellation also stops legacy decoder children."""
import sys


def own_process(process):
    if sys.platform != 'win32': return None
    import win32job
    job=None
    try:
        job=win32job.CreateJobObject(None,'')
        info=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
        info['BasicLimitInformation']['LimitFlags']=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,info)
        win32job.AssignProcessToJobObject(job,process.sentinel)
        return job
    except Exception:
        if job is not None: job.Close()
        process.kill();process.join(timeout=5)
        raise RuntimeError('Could not establish ownership of the Windows worker tree; no investigation started') from None


def stop_process(process,job):
    if job is not None:
        import win32job
        win32job.TerminateJobObject(job,1)
    elif process.is_alive(): process.terminate()
    process.join(timeout=2)
    if process.is_alive():
        process.kill();process.join(timeout=5)
    if process.is_alive(): raise RuntimeError('Worker termination could not be confirmed')
