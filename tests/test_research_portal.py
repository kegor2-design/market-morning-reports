from pathlib import Path
import tempfile
import unittest

from market_morning_publisher.research_portal import build_preview, load_portal_config, validate_theme


ROOT = Path(__file__).resolve().parents[1]


class ResearchPortalThemeTest(unittest.TestCase):
    def test_theme_contract(self):
        result = validate_theme(ROOT / 'blogger_theme' / 'market_morning_research_portal.xml')
        self.assertTrue(result.ok, result)
        self.assertTrue(result.xml_parse_ok)
        self.assertTrue(result.has_blog_widget)
        self.assertTrue(result.has_mobile_breakpoint)
        self.assertTrue(result.blogger_css_enabled)
        self.assertTrue(result.has_home_post_suppression)
        self.assertTrue(result.has_share_suppression)
        text = (ROOT / 'blogger_theme' / 'market_morning_research_portal.xml').read_text(encoding='utf-8')
        for widget in ('BlogSearch', 'Label', 'BlogArchive', 'Profile'):
            self.assertIn("type='%s'" % widget, text)
        self.assertIn("b:css='true'", text)
        self.assertIn('.rp-home .post-body', text)
        self.assertIn('.rp-home .post-share-buttons', text)
        self.assertIn('.rp-item .post-share-buttons', text)
        self.assertIn('decorateResearchCards', text)
        self.assertIn('rp-home-calendar', text)
        self.assertIn('buildCalendar', text)
        self.assertIn("data-rp-theme='1.6.5'", text)

    def test_config_requires_separate_theme_application(self):
        cfg = load_portal_config(ROOT)
        self.assertEqual(cfg['design_direction'], 'ASSET_MANAGER_RESEARCH_PORTAL')
        self.assertFalse(cfg['theme_application']['blogger_api_supports_theme_write'])
        self.assertTrue(cfg['theme_application']['server_deploy_alone_is_not_theme_application'])

    def test_standalone_preview_contains_desktop_and_mobile_post_contract(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'preview.html'
            build_preview(ROOT / 'blogger_theme' / 'market_morning_research_portal.xml', out)
            text = out.read_text(encoding='utf-8')
            for marker in ('rp-home-portal', 'rp-market-board', 'rp-home-calendar', 'rp-intelligence', 'mmp-event-calendar-source', 'mmp-desktop', 'mmp-mobile', 'post-share-buttons', 'sharing-platform-button'):
                self.assertIn(marker, text)

    def test_hotfix_hides_legacy_full_post_and_default_share_dom_on_home(self):
        text = (ROOT / 'blogger_theme' / 'market_morning_research_portal.xml').read_text(encoding='utf-8')
        self.assertRegex(text, r"\.rp-home \.post-body[^\n]*display:none!important")
        self.assertIn('.rp-home .post-share-buttons', text)
        self.assertIn('.rp-home .sharing-platform-button', text)
        self.assertIn("max-width:24px!important", text)
        self.assertIn("Research Portal Theme 1.6.5", text)


if __name__ == '__main__':
    unittest.main()
