import type {Config} from '@docusaurus/types';
import type {Options, ThemeConfig} from '@docusaurus/preset-classic';
import {themes as prismThemes} from 'prism-react-renderer';

const config: Config = {
  title: 'Alyvo Engineering',
  tagline: 'Arquitetura, decisões e operação do Alyvo',
  url: 'http://localhost:8001',
  baseUrl: '/',
  onBrokenLinks: 'throw',
  favicon: 'img/favicon.svg',
  organizationName: 'alyvo',
  projectName: 'alyvo',
  i18n: {
    defaultLocale: 'pt-BR',
    locales: ['pt-BR'],
  },
  markdown: {
    mermaid: true,
  },
  themes: ['@docusaurus/theme-mermaid'],
  presets: [
    [
      'classic',
      {
        docs: {
          path: '../../docs',
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Options,
    ],
  ],
  themeConfig: {
    image: 'img/alyvo-docs-card.svg',
    navbar: {
      title: 'Alyvo Engineering',
      logo: {alt: 'Alyvo', src: 'img/logo.svg'},
      items: [
        {to: '/architecture/overview', label: 'Arquitetura', position: 'left'},
        {to: '/decisions/0001-modular-monolith', label: 'ADRs', position: 'left'},
        {href: 'http://localhost:8000/docs', label: 'Scalar', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Engenharia',
          items: [
            {label: 'Arquitetura', to: '/architecture/overview'},
            {label: 'Decisões ADR', to: '/decisions/0001-modular-monolith'},
            {label: 'Primeiros passos', to: '/getting-started'},
          ],
        },
        {
          title: 'Referências',
          items: [
            {label: 'Scalar API', href: 'http://localhost:8000/docs'},
          ],
        },
      ],
      copyright: `Alyvo Engineering · ${new Date().getFullYear()} · dados sintéticos`,
    },
    colorMode: {
      defaultMode: 'light',
      respectPrefersColorScheme: true,
    },
    mermaid: {
      theme: {light: 'neutral', dark: 'dark'},
      options: {
        themeVariables: {
          fontSize: '17px',
        },
        flowchart: {
          nodeSpacing: 48,
          rankSpacing: 64,
        },
        sequence: {
          actorMargin: 64,
          messageMargin: 42,
        },
      },
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies ThemeConfig,
};

export default config;
