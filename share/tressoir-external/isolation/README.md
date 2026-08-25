# Tressoir isolation starters

These are adaptable starting points. Ask an agent to inspect your project and tailor the chosen
configuration's image, features, extensions, ports, environment, and lifecycle commands to your
actual stack while preserving the boundary described below.

| What you want | Start from | Result |
|---|---|---|
| You and the agent share one Dev Container | `user.devcontainer.json` | The project stays mounted read-write from the host. |
| You stay on the host; the agent is isolated | `agent.devcontainer.json` | The agent gets scratch source plus read-write IB. |
| You and the agent use separate containers | both files | Open each configuration in a separate VS Code window. |

Keep `agent-setup.sh` at `IB/isolation/agent-setup.sh`. The agent template runs it from the mounted
`/workspace/IB` after the container starts.

## Put a template where VS Code finds it

From the project root, copy or adapt the selected file to one of these standard locations:

```text
.devcontainer/user/devcontainer.json
.devcontainer/agent/devcontainer.json
```

Then open the project in VS Code, run **Dev Containers: Reopen in Container** from the Command
Palette, and select the configuration. For separate user and agent containers, open a second VS
Code window on the same project and select the other configuration.

The user configuration uses the normal read-write host-backed workspace, so deleting its container
does not delete project work. The agent configuration mounts host source read-only at `/source`,
creates disposable writable source at `/workspace`, and mounts the host's `IB/` read-write at
`/workspace/IB`. Only work placed in IB automatically reaches the user from that container.

The baseline image supplies a non-root `vscode` user. If the project already has a Dev Container,
adapt that configuration and its development user rather than replacing working project setup.
Do not weaken the agent mount boundary when adapting it.
