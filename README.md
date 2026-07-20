# SteamTime

A Home Assistant custom integration (domain: `steamtime`) — a cooking companion for
steam-oven users. See [`docs/design.md`](docs/design.md) for the technical design and
[`docs/prd-scope-map.md`](docs/prd-scope-map.md) for what carried over from the original
product spec.

Full install/usage instructions land here in the polish pass (design §9, step 9).

Scaffolding is based on [`ludeeus/integration_blueprint`](https://github.com/ludeeus/integration_blueprint):

File | Purpose | Documentation
-- | -- | --
`.devcontainer.json` | Used for development/testing with Visual Studio Code. | [Documentation](https://code.visualstudio.com/docs/remote/containers)
`.github/renovate.json` | Dependency update configuration for Renovate (enabled by default). | [Documentation](https://docs.renovatebot.com/configuration-options/)
`.github/_dependabot.yml` | Dependency update configuration for Dependabot (disabled, see "Dependency updates" below). | [Documentation](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
`.github/ISSUE_TEMPLATE/*.yml` | Templates for the issue tracker | [Documentation](https://help.github.com/en/github/building-a-strong-community/configuring-issue-templates-for-your-repository)
`custom_components/steamtime/*` | Integration files, this is where everything happens. | [Documentation](https://developers.home-assistant.io/docs/creating_component_index)
`CONTRIBUTING.md` | Guidelines on how to contribute. | [Documentation](https://help.github.com/en/github/building-a-strong-community/setting-guidelines-for-repository-contributors)
`LICENSE` | The license file for the project. | [Documentation](https://help.github.com/en/github/creating-cloning-and-archiving-repositories/licensing-a-repository)
`README.md` | The file you are reading now. | [Documentation](https://help.github.com/en/github/writing-on-github/basic-writing-and-formatting-syntax)
`requirements_dev.txt` | Python packages used for development/testing (pulls in lint + test requirements). | [Documentation](https://pip.pypa.io/en/stable/user_guide/#requirements-files)
`requirements_lint.txt` | Python packages used to lint this integration (installed by the Lint CI job). | [Documentation](https://pip.pypa.io/en/stable/user_guide/#requirements-files)
`requirements_test.txt` | Python packages used to run the test suite (`pytest-homeassistant-custom-component`, `mypy`). | [Documentation](https://pip.pypa.io/en/stable/user_guide/#requirements-files)
`requirements_common.txt` | Python packages common to CI and local dev, installed first so any pip upgrade completes before other dependencies. | [Documentation](https://pip.pypa.io/en/stable/user_guide/#requirements-files)

## Dependency updates

This template ships with configuration for **two** dependency update tools. Pick
**one** and remove or disable the other:

- **Renovate** (`.github/renovate.json`) is enabled by default.
- **Dependabot** (`.github/_dependabot.yml`) is included but disabled — the `_`
  prefix means GitHub ignores it. To use Dependabot instead, rename the file
  back to `.github/dependabot.yml` and delete `.github/renovate.json`.

## Development

Run `scripts/develop` to start a local Home Assistant instance with this
integration loaded (config in `config/configuration.yaml`). Run `scripts/lint`
before committing.
