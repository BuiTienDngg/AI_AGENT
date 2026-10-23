"""Package an already exported approved run without regenerating Word or calling AI."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game_seo.core import ROOT,load_json
from game_seo.result_bundle import build_result
from game_seo.translation import validate_translation


def package_existing(work):
    work=Path(work).resolve()
    if not work.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('Run must be inside the project runs directory.')
    manifest=load_json(work/'export_manifest.json')
    qa=load_json(work/'qa_report.json')
    if not qa.get('pass'):
        raise ValueError('Run has no passing deterministic QA.')
    article=load_json(work/'article.json')
    translation=load_json(work/'translation_vi.json')
    modern=load_json(work/'editorial_policy.json',default={}).get('profile')=='gameplay_first_v2'
    if not validate_translation(article,translation,localize_title=modern)['pass']:
        raise ValueError('Existing EN/VI documents do not have aligned source data.')
    return build_result(article,translation,load_json(work/'images.json')['images'],
                        load_json(work/'frames.json'),manifest['files'],work)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True)
    print(package_existing(parser.parse_args().run_dir))
