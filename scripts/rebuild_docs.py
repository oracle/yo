#!/usr/bin/env python3
import yo.main

DIRECTIVE_FMT = """.. argparse::
   :module: yo.main
   :func: cmd_{stdname}_args
   :prog: yo {name}"""


def main():
    cmds = yo.main.YoCmd.iter_commands()
    group_to_cmd = {}
    for cmd in cmds:
        group_to_cmd.setdefault(cmd.group, []).append(cmd)

    for group, cmds in group_to_cmd.items():
        cmds.sort(key=lambda c: c.name)

    trans = str.maketrans(" -", "__")

    for i, group in enumerate(yo.main.COMMAND_GROUP_ORDER):
        with open(f"doc/cmds/cmd{i:02d}.rst", "w") as f:
            # f.write(f".. _{group}::\n\n")
            f.write(group + "\n")
            f.write("=" * len(group) + "\n\n")
            for j, cmd in enumerate(group_to_cmd[group]):
                if j > 0:
                    f.write("\n\n")
                stdname = cmd.name.translate(trans)
                directive = DIRECTIVE_FMT.format(
                    name=cmd.name,
                    stdname=stdname,
                )
                f.write(f".. _yo_{stdname}:\n\n")
                f.write(f"yo {cmd.name}\n")
                f.write("-" * (len(cmd.name) + 3) + "\n\n")
                f.write(directive + "\n")

    with open("doc/cmds/index.rst", "r+") as f:
        contents = f.read()
        ix = contents.index("Overview\n")
        f.seek(ix)
        f.truncate(ix)
        f.write("Overview\n--------\n\n")

        for group in yo.main.COMMAND_GROUP_ORDER:
            f.write(group + ":\n\n")
            for cmd in group_to_cmd[group]:
                stdname = cmd.name.translate(trans)
                help = getattr(cmd, "help", cmd.description.strip())
                f.write(f"  - :ref:`yo_{stdname}` - {help}\n")
            f.write("\n")

        f.write("Command Group Index\n-------------------\n\n")
        f.write(".. toctree::\n   :maxdepth: 1\n\n")
        for group_idx in range(len(yo.main.COMMAND_GROUP_ORDER)):
            f.write(f"   cmd{group_idx:02d}\n")


if __name__ == "__main__":
    main()
