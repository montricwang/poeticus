// Poeticus commit format: English Conventional Commits with a required scope.
const ascii = /^[\x20-\x7E]*$/;
export default {
  rules: {
    'type-enum': [
      2,
      'always',
      ['build', 'chore', 'ci', 'docs', 'feat', 'fix', 'perf', 'refactor', 'revert', 'style', 'test'],
    ],
    'type-empty': [2, 'never'],
    'scope-empty': [2, 'never'],
    'subject-empty': [2, 'never'],
    'subject-case': [2, 'never', ['start-case', 'pascal-case', 'upper-case']],
    'header-max-length': [2, 'always', 100],
    'header-ascii': [2, 'always'],
    'body-ascii': [2, 'always'],
    'footer-ascii': [2, 'always'],
    'body-leading-blank': [2, 'always'],
    'footer-leading-blank': [2, 'always'],
  },
  plugins: [
    {
      rules: {
        'header-ascii': ({ header }) => [ascii.test(header ?? ''), 'use an English ASCII commit header'],
        'body-ascii': ({ body }) => [asciiMultiline(body), 'use an English ASCII commit body'],
        'footer-ascii': ({ footer }) => [asciiMultiline(footer), 'use an English ASCII commit footer'],
      },
    },
  ],
};
function asciiMultiline(value) {
  return (value ?? '').split('\n').every((line) => ascii.test(line));
}
