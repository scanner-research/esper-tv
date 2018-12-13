from esper.prelude import *
from collections import defaultdict
from functools import reduce
import inspect
import os

queries = []


def query(name):
    frame = inspect.stack()[1]
    module = inspect.getmodule(frame[0])
    filename = module.__file__

    def wrapper(f):
        lines = inspect.getsource(f).split('\n')
        lines = lines[:-1]  # Seems to include a trailing newline

        # Hacky way to get just the function body
        i = 0
        while True:
            if "():" in lines[i]:
                break
            i = i + 1

        fn = lines[i:]
        fn += ['FN = ' + f.__name__]
        queries.append([name, '\n'.join(fn)])

        return f

    return wrapper

from .all_faces import *
from .all_videos import *
from .panels_sql import *
from .panels_rekall import *
from .interview_with_person_x import *
from .sandbox_labels import *
from .other_queries import *
