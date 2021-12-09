from setuptools import setup

setup(name='dc6006l',
      version='0.0.1',
      description='CLI/library to control FNIRSI DC Power Supply (DC-6006L, etc).',
      long_description=open('README.md').read(),
      url='https://github.com/tai/dc6006l/',
      author='Taisuke Yamada',
      author_email='tai@remove-if-not-spam.rakugaki.org',
      license='MIT',
      packages=['dc6006l'],
      entry_points = '''
[console_scripts]
dc6006l=dc6006l:main
''',
      classifiers=[
          'License :: OSI Approved :: MIT License',
          'Intended Audience :: Developers',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Topic :: Scientific/Engineering',
          'Topic :: Software Development :: Embedded Systems',
          'Topic :: System :: Hardware',
      ],
      install_requires=[
          'pyserial',
          'argparse',
      ]
)
