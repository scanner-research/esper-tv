"""Parallel Rekall Runtime specialized for Esper and Django.

Rekall Runtime Factories:
    get_runtime_for_ipython_cluster: Returns a runtime using an ipython cluster
        (ipyparallel) as worker processes. Best option in Jupyter Notebook.
    get_runtime_for_script: Returns a parallel runtime that is safe
        in a multithreaded program, but does not work in Jupyter Notebook.
    get_runtime_for_jupyter: Returns a parallel runtime that works in Jupyter
        Notebook but the usual caveats of forking a multithreaded program still
        apply.

WorkerPool Factories:
    get_worker_pool_factory_for_ipython_cluster: Returns a factory of
        IPythonClusterPool.
    get_worker_pool_factory_for_script: Returns a factory of SpawnedProcessPool
        that sets up django correctly in the child process.
    get_worker_pool_factory_for_jupyter: Returns a factory of ForkedProcessPool
        that allows child processes to talk to django database concurrently.

WorkerPool Implementations:
    IPythonClusterPool: A worker pool using an existing ipython cluster as
        workers.
"""
import django
import cloudpickle
import multiprocessing as mp
import os
import ipyparallel
import traceback

from rekall.runtime import (
        AbstractWorkerPool,
        AbstractAsyncTaskResult,
        TaskException,
        Runtime,
        SpawnedProcessPool,
        get_forked_process_pool_factory,
        get_spawned_process_pool_factory)

def get_worker_pool_factory_for_jupyter(num_workers=mp.cpu_count()):
    """Returns factory of ForkedProcessPool that works with django."""
    fork_factory = get_forked_process_pool_factory(num_workers)
    # Forked Django Database connections will not work. Hence we close all
    # connections before forking to allow child processes to establish their
    # own connections.
    def worker_pool_factory(fn):
        django.db.connections.close_all()
        return fork_factory(fn)
    return worker_pool_factory

def get_runtime_for_jupyter(num_workers=mp.cpu_count()):
    """Returns a parallel runtime that works in Jupyter Notebook.
    
    Notes:
        This uses ForkedProcessPool so the usual caveats of forking a
        multithreaded program apply.
    """
    return Runtime(get_worker_pool_factory_for_jupyter(num_workers))

def _set_up_django():
    # set up django context
    import django
    django.setup()

def get_worker_pool_factory_for_script(num_workers=mp.cpu_count()):
    """Returns factory of SpawnedProcessPool that works with django."""
    def worker_pool_factory(fn):
        return SpawnedProcessPool(fn, num_workers, initializer=_set_up_django)
    return worker_pool_factory

def get_runtime_for_script(num_workers=mp.cpu_count()):
    """Returns a parallel runtime that is safe for multithreaded programs.

    Notes:
        This uses SpawnedProcessPool and it does not work in a Jupyter
        Notebook. It will hang in Jupyter.
    """
    return Runtime(get_worker_pool_factory_for_script(num_workers))

def _annotate_future(future, vids, done):
    # Ipyparallel futures return chunked results. Since we set the chunksize
    # to 1, future.get() returns a tuple of size 1.
    class ChunkedFutureWrapper(AbstractAsyncTaskResult):
        def __init__(self, chunked_future):
            self._f = chunked_future

        def get(self):
            try:
                for result in self._f.get():
                    return result
            except ipyparallel.RemoteError as e:
                raise TaskException() from e

        def done(self):
            return self._f.ready()

    def cb(f):
        e = f.exception()
        done(vids, e)
    future.add_done_callback(cb)
    return ChunkedFutureWrapper(future)

class IPythonClusterPool(AbstractWorkerPool):
    """WorkerPool Implementation using an ipython cluster."""
    def __init__(self, client, fn):
        """Initializes with an ipython cluster client and the function to run.

        Args:
            client (ipyparallel.Client): client to the cluster.
            fn: The function to run in workers.
        """
        self._client = client
        self._fn = fn

    def shut_down(self):
        # The cluster is long running process and should not be shut down.
        pass

    def map(self, tasks, done):
        view = self._client.load_balanced_view()
        amr = view.map(self._fn, tasks, ordered=False, chunksize=1)
        task_ids = amr.msg_ids
        assert(len(tasks) == len(task_ids))
        return  [_annotate_future(self._client.get_result(tid), vids, done)
                   for vids, tid in zip(tasks, task_ids)]

def get_worker_pool_factory_for_ipython_cluster(client):
    """Returns a factory for IPythonClusterPool.

    Args:
        client (ipyparallel.Client): client to the cluster.

    Returns:
        A factory for IPythonClusterPool

    Raises:
        RuntimeError: If no worker can be found in the cluster.
    """
    if len(client) == 0:
        raise RuntimeError("There is no worker in the cluster")
    client.direct_view().use_cloudpickle()
    def factory(fn):
        return IPythonClusterPool(client, fn)
    return factory

def get_runtime_for_ipython_cluster(client):
    """Returns a runtime using an ipython cluster as worker processes. 
    
    This is the best option in a Jupyter Notebook.
    """
    return Runtime(get_worker_pool_factory_for_ipython_cluster(client))
