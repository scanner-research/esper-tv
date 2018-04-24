from setuptools import setup
from setuptools_rust import Binding, RustExtension

setup(
    name='rust-scripts',
    version='1.0',
    rust_extensions=[
        RustExtension('rust_scripts._rustscripts', 'Cargo.toml', binding=Binding.PyO3)
    ],
    packages=['rust_scripts'],
    # rust extensions are not zip safe, just like C-extensions.
    zip_safe=False)
