from setuptools import setup, find_packages

static_files = ['extension', 'jupyter', 'common']

setup(
    name='esper_jupyter',
    version='0.1.0',
    data_files=[
        ('share/jupyter/nbextensions/esper_jupyter', sum([
            ['esper_jupyter/static/{}.js'.format(f),
             'esper_jupyter/static/{}.js.map'.format(f)]
            for f in static_files
        ], []),),
        ('etc/jupyter/nbconfig/notebook.d/' ,['esper_jupyter.json'])
    ],
    install_requires=[
        'ipywidgets >= 7.0.0'
    ],
    zip_safe=False,
    packages=find_packages()
)
