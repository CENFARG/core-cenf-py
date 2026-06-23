import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      collapsible: true,
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/quick-start',
      ],
    },
    {
      type: 'category',
      label: 'Core Concepts',
      collapsible: true,
      collapsed: false,
      items: [
        'core-concepts/ports-and-adapters',
        'core-concepts/context-propagation',
        'core-concepts/agent-experience',
      ],
    },
    {
      type: 'category',
      label: 'Managers',
      collapsible: true,
      collapsed: true,
      items: [
        'managers/config-manager',
        'managers/logger-manager',
        'managers/secret-manager',
        'managers/error-handling-manager',
        'managers/observability-manager',
        'managers/auth-manager',
        'managers/cache-manager',
        'managers/database-manager',
        'managers/file-storage-manager',
        'managers/task-queue-manager',
        'managers/external-api-manager',
        'managers/feature-flag-manager',
        'managers/dependency-manager',
        'managers/dynamic-prompting-manager',
        'managers/alert-manager',
        'managers/ratelimit-manager',
        'managers/i18n-manager',
        'managers/permission-manager',
        'managers/licence-manager',
        'managers/update-manager',
        'managers/bus-event-manager',
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      collapsible: true,
      collapsed: false,
      items: [
        'guides/bootstrap-guide',
        'guides/testing-guide',
      ],
    },
  ],

  apiSidebar: [
    {
      type: 'category',
      label: 'API Reference',
      collapsible: false,
      items: [
        'reference/api/overview',
      ],
    },
  ],
};

export default sidebars;
