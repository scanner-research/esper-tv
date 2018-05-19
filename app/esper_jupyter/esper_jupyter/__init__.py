from .main import *

def _jupyter_nbextension_paths():
    return [{
        'section': 'notebook',
        'src': 'static',
        'dest': 'esper_jupyter',
        'require': 'esper_jupyter/extension'
    }]
