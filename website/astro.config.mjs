// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://supernova1963.github.io',
	base: '/eedc-homeassistant',
	integrations: [
		starlight({
			title: 'EEDC',
			description: 'Energie Effizienz Data Center – PV-Analyse mit optionaler Home Assistant Integration',
			locales: {
				root: { label: 'Deutsch', lang: 'de' },
			},
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/supernova1963/eedc-homeassistant' },
			],
			logo: {
				src: './src/assets/eedc-icon.png',
				replacesTitle: false,
			},
			customCss: [
				'./src/styles/custom.css',
			],
			sidebar: [
				{
					label: 'Startseite',
					slug: 'index',
				},
				{
					label: 'Projekt',
					items: [
						{ label: 'Features', slug: 'features' },
						{ label: 'Installation', slug: 'installation' },
						{ label: 'Support', slug: 'support' },
						{ label: 'Über das Projekt', slug: 'ueber' },
					],
				},
				{
					label: 'Benutzerhandbuch',
					items: [
						{ label: 'Übersicht', slug: 'benutzerhandbuch' },
						{ label: 'Teil I: Installation & Einrichtung', slug: 'handbuch-installation' },
						{ label: 'Teil II: Bedienung', slug: 'handbuch-bedienung' },
						{ label: 'Teil III: Einstellungen', slug: 'handbuch-einstellungen' },
						{ label: 'Modul: Infothek', slug: 'handbuch-infothek' },
						{ label: 'Glossar', slug: 'glossar' },
					],
				},
				{
					label: 'Dokumentation',
					items: [
						{ label: 'Architektur', slug: 'architektur' },
						{ label: 'Berechnungsreferenz', slug: 'berechnungen' },
						{ label: 'Entwicklung', slug: 'entwicklung' },
						{ label: 'Dev-Machine Setup', slug: 'setup-devmachine' },
					],
				},
				{
					label: 'Changelog',
					slug: 'changelog',
				},
				{
					label: 'Rechtliches',
					items: [
						{ label: 'Impressum', slug: 'impressum' },
						{ label: 'Datenschutz', slug: 'datenschutz' },
					],
				},
			],
		}),
	],
});
