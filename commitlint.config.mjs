// Commitlint rules are self-contained: local npx usage needs only @commitlint/cli.
export default {
  rules: {
    'type-enum': [
      2,
      'always',
      ['build', 'chore', 'ci', 'docs', 'feat', 'fix', 'perf', 'refactor', 'revert', 'style', 'test'],
    ],
    'type-empty': [2, 'never'],
    'subject-empty': [2, 'never'],
    'subject-case': [2, 'never', ['start-case', 'pascal-case', 'upper-case']],
    'header-max-length': [2, 'always', 100],
    'header-ascii': [2, 'always'],
    'body-leading-blank': [2, 'always'],
    'footer-leading-blank': [2, 'always'],
  },
  plugins: [
    {
      rules: {
        'header-ascii': ({ header }) => [
          /^[\x20-\x7E]+$/.test(header ?? ''),
          'commit header must contain ASCII characters only (use English)',
        ],
      },
    },
  ],
};
