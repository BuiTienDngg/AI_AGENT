"""Trusted project-owner declarations, separate from untrusted research evidence."""
from __future__ import annotations


def developer_authorship_allowed(cfg):
    return cfg.get('brand_role') == 'developer' and cfg.get('developer_authorship_confirmed') is True


def brand_context(cfg):
    return {
        'publisher': cfg.get('publisher', 'Slope3'),
        'website': cfg.get('brand_website', ''),
        'role': cfg.get('brand_role', 'publisher'),
        'developer_authorship_confirmed': developer_authorship_allowed(cfg),
        'concept_narrative_authorized': (
            developer_authorship_allowed(cfg) and cfg.get('concept_narrative_authorized') is True
        ),
        'declaration_source': 'project owner configuration',
        'scope': 'The product supplied for this project run; not every game or IP mentioned in research.',
        'voice': 'Official first-person developer voice' if developer_authorship_allowed(cfg) else 'Official publisher voice',
        'concept_direction': (
            'Build the opening from relevant researched real-world context. Develop that context into '
            'our product concept, then explain how our observed gameplay, visual choices, story and '
            'player experience express the same idea. Keep these connections brief and useful; '
            'Gameplay and Controls prioritize clear player actions, confirmed rules and results. '
            'Do not repeat design intentions in every paragraph. This is the owner-authorized creative product '
            'narrative, not a recovered documentary history.'
        ),
        'limits': (
            'Do not invent studio visits, personal memories, dates, playtests, user metrics, technical '
            'implementation, controls or power-up effects. Visual similarity does not confirm a '
            'product identity or transfer authorship of another named IP. Keep uncertainty private.'
        ),
    }
