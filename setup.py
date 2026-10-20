from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
RESEARCH_MODULES = [
    'shnifter_cli', 'shnifter_replay', 'shnifter_backtest_cli',
    'shnifter_analysis_core', 'shnifter_actions', 'shnifter_agent_cli',
    'shnifter_agent_api', 'shnifter_agent_mcp', 'shnifter_experiments',
    'shnifter_experiment_cli', 'shnifter_oos_gate', 'shnifter_research_cli',
    'shnifter_paper_ledger', 'shnifter_paper_cli', 'shnifter_safe_output',
    'shnifter_order_events', 'shnifter_order_events_cli', 'shnifter_paths',
]

PACKAGE_MODULES = {
    'core': {'data_models'},
    'providers': {'yfinance_provider'},
    'shnifterBB': {'shnifter_bb'},
}

class ResearchBuild(build_py):
    """Do not accidentally ship neighbouring GUI/account/prototype modules."""
    def find_package_modules(self, package, package_dir):
        return [(pkg, mod, filename) for pkg, mod, filename in
                super().find_package_modules(package, package_dir)
                if mod in PACKAGE_MODULES.get(pkg, set())]

setup(
    name='shnifter-trader',
    version='0.2.0a1',
    author='KingAiCodeForge',
    description='Experimental offline research and explicit local paper simulation',
    long_description=(ROOT / 'README.md').read_text(encoding='utf-8'),
    long_description_content_type='text/markdown',
    url='https://github.com/KingAiCodeForge/shnifter-trader',
    # Deliberately exclude the copied framework, GUI prototypes and local data.
    # Historical CLI uses only these small namespace packages.
    packages=['core', 'providers', 'shnifterBB'],
    py_modules=RESEARCH_MODULES,
    python_requires='>=3.11',
    install_requires=['numpy>=2.1', 'pandas>=2.2.3', 'scikit-learn>=1.6',
                      'pydantic>=2', 'requests>=2.31'],
    extras_require={
        'market': ['yfinance>=0.2.28'],
        'api': ['fastapi>=0.104', 'uvicorn>=0.24'],
        'agents': ['mcp>=1.29,<3'],
        'gui': ['PySide6>=6.8', 'matplotlib>=3.9', 'nltk>=3.8.1',
                'plotly>=6.2', 'aiolimiter>=1.2', 'tqdm>=4.67'],
        'dev': ['build>=1.2', 'pytest>=7.4'],
    },
    classifiers=['Development Status :: 3 - Alpha',
                 'Programming Language :: Python :: 3',
                 'Topic :: Scientific/Engineering :: Information Analysis'],
    entry_points={'console_scripts': ['shnifter-trader=shnifter_cli:main']},
    include_package_data=False,
    cmdclass={'build_py': ResearchBuild},
)
