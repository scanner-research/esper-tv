import ipywidgets as widgets
from traitlets import Unicode, Dict, List

# traitlets: https://ipywidgets.readthedocs.io/en/latest/examples/Widget%20Custom.html#Other-traitlet-types

@widgets.register
class EsperWidget(widgets.DOMWidget):
    _view_name = Unicode('EsperView').tag(sync=True)
    _view_module = Unicode('esper_jupyter').tag(sync=True)
    result = Dict({}).tag(sync=True)
    jsglobals = Dict({}).tag(sync=True)
    settings = Dict({}).tag(sync=True)
    selected = List([]).tag(sync=True)
