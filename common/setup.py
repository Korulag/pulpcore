from setuptools import setup, find_packages

setup(
    name='pulp-common',
    version='2.11a1',
    license='GPLv2+',
    packages=find_packages(exclude=['test']),
    author='Pulp Team',
    author_email='pulp-list@redhat.com',
)
