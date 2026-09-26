import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('media_lifecycle',Path(__file__).parents[1]/'media_lifecycle.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_only_applicant_files_expire():
    rules=module.hiring_media_lifecycle()['rule']
    def expires(path,days):
        return any(days>=r['condition']['age'] and any(path.startswith(p) for p in r['condition']['matchesPrefix']) for r in rules)
    for prefix in ('hiring_cv/','cookcredit-skill/','skill_videos/'):
        assert not expires(prefix+'file',29)
        assert expires(prefix+'file',30)
    assert not expires('company_branding/active/logo.png',3650)
