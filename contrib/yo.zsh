#compdef yo

local -A opt_args
local -a reply

# yo common {{{
local -a _yo_single_instance_options=(
  '(-n --name)'{-n+,--name=}'[Name of the instance to filter by]'
  '(-E --exact-name)'{-E,--exact-name}'[Do not prefix the instance name with your username]'
  '--no-exact-name[Always not prefix the instance name with your username]'
)
_yo_single_instance_command() { _arguments -S $_yo_single_instance_options '1:instance:_yo_instances' }
local -a yo_single_instance_command=(/$'[^\0]#\0'/ ': : :_yo_context _yo_single_instance_command' '#')

local -a _yo_multi_instance_options=(
  '--all[Act on all instances]'
  '(-E --exact-name)'{-E,--exact-name}'[Do not prefix the instance name with your username]'
  '--no-exact-name[Always prefix the instance name with your username]'
  '(-y --yes)'{-y,--yes}'[Do not prompt for confirmation]'
)
_yo_multi_instance_command() { _arguments -S $_yo_multi_instance_options '*:instance:_yo_instances' }
local -a yo_multi_instance_command=(/$'[^\0]#\0'/ ': : :_yo_multi_instance_command' '#')

local -a _yo_maybe_ssh_instance_options=(
  '(-s --ssh)'{-s,--ssh}'[SSH to the instance once it is running]'
)
_yo_maybe_ssh_instance_command() {
  _arguments -S $_yo_multi_instance_options $_yo_maybe_ssh_instance_options '*:instance:_yo_instances'
}
local -a yo_maybe_ssh_instance_command=(/$'[^\0]#\0'/ ': : :_yo_maybe_ssh_instance_command' '#')

local -a _yo_remote_desktop_options=(
  '(-T --no-tunnel)'{-T,--no-tunnel}'[Do not tunnel the connection over SSH]'
)
_yo_remote_desktop_command() {
  _arguments -S $_yo_remote_desktop_options $_yo_single_instance_options '1:instance:_yo_instances'
}
local -a yo_remote_desktop_command=(/$'[^\0]#\0'/ ': : :_yo_context _yo_remote_desktop_command' '#')

_yo_context() {
  # This makes nested _arguments calls a little simpler
  if ! compset -N argument-rest; then
    _message "no more arguments"
    return 1
  fi
  # compadd flags are prepended by _regex_arguments
  local fn="$@[-1]"
  local curcontext="${curcontext%:*:*}:yo-${${${fn%_command}#_yo_}//_/-}:"
  shift -p 1
  "$fn" "$@"
}
# }}}
# yo resources  {{{
_yo_maybe_msg_resource_err() {
  local rcode=$1 resource=$2; shift 2
  case $rcode in
    127 ) _message "$resource completion requires jq";;
    <1->) _message "failed to parse $resource names from $@";;
  esac
}

_yo_instances() {
  local filter='.instances.cache[] | select(.state != "TERMINATED") | "\(.name | gsub(":"; "\\:")):\(.shape) [\(.state)]"'
  local -Ua instances; instances=(${(@f)"$(_call_program -l yo-instances jq -r ${(q)filter} $caches)"})
  _yo_maybe_msg_resource_err $status "instance" $caches
  if [[ -z ${exact_name:-${opt_args[(I)-E|--exact-name]}} ||
        -n ${exact_name+$opt_args[(I)--no-exact-name]} ]]; then
          instances+=(${instances#$USER-})
  fi

  _describe -t yo-instances "instance" instances "$@"
}

_yo_shapes() {
  local filter='.shapes.cache[] | "\(.name):\(.name ) / \(.memory_in_gbs)GB"
    + if .local_disks > 0 then " / \(.local_disks_total_size_in_gbs)GB \(.local_disk_description)" else "" end'
  local -a shapes; shapes=(${(@f)"$(_call_program -l yo-shapes jq -r ${(q)filter} $caches)"})
  _yo_maybe_msg_resource_err $status "shape" $caches

  _describe -t yo-shapes "shape" shapes -M 'm:{[:lower:]}={[:upper:]} r:|.=*' "$@"
}

_yo_images() {
  local filter_os='.images.cache[] | select(.os != "Custom" and .os_version != "Custom") | "\(.os):\(.os_version)"'
  local filter_name='.images.cache[] | select(.os != "Custom" and .os_version != "Custom").name | gsub(":"; "\\:")'
  local filter_custom='.images.cache[] | select(.os == "Custom" or .os_version == "Custom").name | gsub(":"; "\\:")'
  local -a images_os images_custom images_named


  local expl ret=1
  _tags yo-images-os yo-images-custom yo-images-named
  while _tags; do
    if _requested yo-images-os; then
      ((#images_os)) || images_os=(${(@f)"$(_call_program -l yo-images-os jq -r ${(q)filter_os} $caches)"})
      _yo_maybe_msg_resource_err $status "OS image" $caches
     _all_labels yo-images-os expl "OS image" _multi_parts -i : images_os && ret=0
    fi
    if _requested yo-images-custom; then
      ((#images_custom)) || images_custom=(${(@f)"$(_call_program -l yo-images-custom jq -r ${(q)filter_custom} $caches)"})
      _yo_maybe_msg_resource_err $status "custom image" $caches
     _all_labels yo-images-custom expl "custom image" compadd -a - images_custom && ret=0
    fi
    if ((ret)) && _requested yo-images-named; then
      ((#images_named)) || images_named=(${(@f)"$(_call_program -l yo-images-named jq -r ${(q)filter_name} $caches)"})
      _yo_maybe_msg_resource_err $status "named image" $caches
      _all_labels yo-images-named expl "named image" compadd -a - images_named && ret=0
    fi
    ((ret)) || break
  done
  return ret
}

_yo_volumes() {
  local filter='.bootvols.cache[] | select(.state != "TERMINATED") |
    "\(.name | gsub(":"; "\\:")):\(.name | gsub(":"; "\\:")) \(.size_in_gbs)GB [\(.state)]"'
  local -a volumes; volumes=(${(@f)"$(_call_program -l yo-volumes jq -r ${(q)filter} $caches)"})
  _yo_maybe_msg_resource_err $status "volume" $caches

  _describe -t yo-volumes "volume" volumes "$@"
}

_yo_ads() {
  local filter='.ads.cache[].name | gsub(":"; "\\:")'
  local -a ads; ads=(${(@f)"$(_call_program -l yo-ads jq -r ${(q)filter} $caches)"})
  _yo_maybe_msg_resource_err $status "availability domain" $caches

  _describe -t yo-ads "availability domain" ads "$@"
}

_yo_tasks() {
  local expl
  local -a task_builtin=(drgn ocid)
  _wanted yo-tasks expl "task" _path_files "$@" -g ~/.oci/yo-tasks/'*(N.r:t)'
  _wanted yo-builtin-tasks expl "builtin task" compadd "$@" -a - task_builtin
}
# }}}
# yo basic {{{
_yo_list_command() {
  local -a columns=(Name Shape CPU Mem State AD Created IP ResourceType)
  local -a _yo_list_options=(
    '(-c --cached)'{-c,--cached}'[Avoid loading and calling OCI]'
    '(-C --columns)'{-C+,--columns=}'[Specify all columns in the table]:column:('"$columns"')'
    \*{-x+,--extra-column=}'[Add a column to the table]:column:('"$columns"')'
    '(-i --ip)'{-i,--ip}'[Include the IP address column]'
    '--ad[Include the availability domain column]'
    '(-a --all)'{-a,--all}'[Display all instances in the compartment]'
  )
  _arguments -S -A '*' $_yo_list_options
}
local -a yo_list_command=(/$'[^\0]#\0'/ ':yo-list: :_yo_list_command' '#')

_yo_launch_command() {
  local -a _yo_launch_options=(
    '(-n --name)'{-n+,--name=}'[Name to give the instance]'
    '--os=[Operating system and version]'
    '--image=[Display name of a custom image in the compartment]:image:_yo_images'
    '(-V --volume)'{-V+,--volume=}'[Specify a boot volume]:volume:_yo_volumes'
    '(-S --shape)'{-S+,--shape=}'[Specify the shape to use]:shape:_yo_shapes'
    '--boot-volume-size-gbs=[Specify the boot volume size]'
    '--mem=[Specify the memory size]:memory:_numbers -t memory -u GiB -f'
    '--cpu=[Specify the CPU count]:cpus:_numbers'
    '--ad=[Specify the availability domain]:availability domain:_yo_ads'
    '(-w --wait)'{-w,--wait}'[Wait for the instance to start]'
    '(-s --ssh)'{-s,--ssh}'[Wait for the instance to be reachable by ssh]'
    '(-E --exact-name)'{-E,--exact-name}'[Do not prefix the instance name with your username]'
    '--no-exact-name[Always not prefix the instance name with your username]'
    '--dry-run[Do not launch an instance, but print what would be done]'
    '(-p --profile)'{-p+,--profile=}'[Profile to use]:profile:('"$_yo_profiles"')'
    \*{-t+,--task=}'[Tasks to run once the instance is up]:task:_yo_tasks'
    '--load-image=[Strategy for loading images]:strategy:(UNIQUE LATEST)'
    '(-u --username)'{-u+,--username=}'[Username for logging into the instance]:user:_users'
  )
  _arguments -S -A '*' $_yo_launch_options
}
local -a yo_launch_command=(/$'[^\0]#\0'/ ':yo-launch: :_yo_launch_command' '#')

_yo_ssh_command() {
  local -a _yo_ssh_options=(
    '(-w --wait)'{-w,--wait}'[Wait for ssh access]'
    '(-A --agent)'{-A,--agent}'[Forward SSH agent]'
    '--ssh-args=[Arguments to pass to ssh]'
    '(-s --start)'{-s,--start}'[Start the instance if not already started]'
    '(-q --quiet)'{-q,--quiet}'[Reduce informative output]'
  )

  _arguments -S \
    $_yo_ssh_options \
    $_yo_single_instance_options \
    '1:instance:_yo_instances' \
    '*:: := {words[1]=ssh; _normal}'
}
local -a yo_ssh_command=(/$'[^\0]#\0'/ ':yo-ssh: :_yo_context _yo_ssh_command' '#')

local -a _yo_basic_commands=(
  'list:List your OCI instances:$yo_list_command'
  'la*unch:Launch an OCI instance:$yo_launch_command'
  'ssh:SSH into an instance:$yo_ssh_command'
)
_regex_words yo-basic-commands 'yo basic command' $_yo_basic_commands
local -a _yo_basic=("$reply[@]")
# }}}
# yo instance {{{
local -a _yo_instance_states=(PROVISIONING STARTING RUNNING STOPPED SAVED)

_yo_rebuild_command() {
  local -a _yo_rebuild_options=(
    '(-n --name)'{-n+,--name=}'[Name of the instance in a saved state]'
    '(-E --exact-name)'{-E,--exact-name}'[Do not prefix the instance name with your username]'
    '(-w --wait)'{-w,--wait}'[Wait for the instance to start]'
    '(-s --ssh)'{-s,--ssh}'[SSH to the instance once it is running]'
  )
  _arguments -S -A '*' $_yo_rebuild_options
}
local -a yo_rebuild_command=(/$'[^\0]#\0'/ ':yo-rebuild: :_yo_rebuild_command' '#')

_yo_wait_command() {
  local -a _yo_wait_options=(
    '(-s --state)'{-s+,--state=}'[State to wait for]:state:('"$_yo_instance_states"')'
    '--timeout=[How long to wait in seconds]:timeout:()'
  )

  _arguments -S \
    $_yo_single_instance_options \
    $_yo_wait_options \
    '1:instance:_yo_instances'
}
local -a yo_wait_command=(/$'[^\0]#\0'/ ':yo-wait: :_yo_context _yo_wait_command' '#')

_yo_teardown_command() {
  local -a _yo_teardown_options=(
    '(-y --yes)'{-y,--yes}'[Do not prompt for confirmation]'
  )

  _arguments -S \
    $_yo_single_instance_options \
    $_yo_teardown_options \
    '1:instance:_yo_instances'
}
local -a yo_teardown_command=(/$'[^\0]#\0'/ ':yo-teardown: :_yo_context _yo_teardown_command' '#')

_yo_rename_command() {
  _arguments -S \
    $_yo_single_instance_options \
    '1:instance:_yo_instances' \
    '2:new name:()'
}
local -a yo_rename_command=(/$'[^\0]#\0'/ ':yo-rename: :_yo_context _yo_rename_command' '#')

_yo_protect_command() {
  _arguments -S \
    $_yo_single_instance_options \
    '1:instance:_yo_instances' \
    '2:protection setting:(on off)'
}
local -a yo_protect_command=(/$'[^\0]#\0'/ ':yo-protect: :_yo_context _yo_protect_command' '#')

_yo_terminate_command() {
  local -a _yo_terminate_options=(
    '(-p --preserve-volume)'{-p,--preserve-volume}'[Do not remove the root volume for this instace]'
    '(-P --no-preserve-volume)'{-P,--no-preserve-volume}'[Remove the root volume for this instace]'
    '--dry-run[Do not terminate an instance, but print what would be done]'
    '(-w --wait)'{-w,--wait}'[Wait for instance state TERMINATED]'
  )

  _arguments -S \
    $_yo_multi_instance_options \
    $_yo_terminate_options \
    '*:instance:_yo_instances'
}
local -a yo_terminate_command=(/$'[^\0]#\0'/ ':yo-terminate: :_yo_context _yo_terminate_command' '#')

_yo_resize_command() {
  local -a _yo_resize_options=(
    '(-S --shape)'{-S+,--shape=}'[Instance shape to select]:shape:_yo_shapes'
  )
  _arguments -S \
    $_yo_maybe_ssh_instance_options \
    $_yo_resize_options \
    '1:instance:_yo_instances'
}
local -a yo_resize_command=(/$'[^\0]#\0'/ ':yo-resize: :_yo_context _yo_resize_command' '#')

local -a _yo_instance_commands=(
  'rebuild:Rebuild a saved and torn down instance:$yo_rebuild_command'
  'wait:Wait for an instance to enter a state:$yo_wait_command'
  'tear*down:Save block volume and instance metadata, then terminate:$yo_teardown_command'
  'rename:Give an instance a new name:$yo_rename_command'
  'prot*ect:Enable or disable Yo’s termination protection:$yo_protect_command'
  'term*inate:Terminate one or more instances:$yo_terminate_command'
  'stop:Stop (shut down) one or more OCI instances:$yo_multi_instance_command'
  'nmi:Send diagnostic interrupt (NMI) to one or more instance (dangerous):$yo_multi_instance_command'
  'reboot:Reboot one or more OCI instances:$yo_maybe_ssh_instance_command'
  'start:Start (boot up) one or more OCI instances:$yo_maybe_ssh_instance_command'
  'res*ize:Resize (change shape) and reboot an OCI instance:$yo_resize_command'
)
_regex_words yo-instance-commands 'yo instance command' $_yo_instance_commands
local -a _yo_instance=("$reply[@]")
# }}}
# yo interactive {{{
_yo_ip_command() {
  local -a _yo_ip_options=(
    '(-E --exact-name)'{-E,--exact-name}'[Do not prefix the instance name with your username]'
    '--no-exact-name[Always prefix the instance name with your username]'
  )
  _arguments -S -A '*' $_yo_ip_options '*:instance:_yo_instances'
}
local -a yo_ip_command=(/$'[^\0]#\0'/ ':yo-ip: :_yo_ip_command' '#')

_yo_scp_service() {
  _alternative \
    'yo-instances:instance:_yo_instances -S:' \
    ' : :{words[1]=scp; _normal}'
}

_yo_scp_command() {
  _arguments -S \
    $_yo_single_instance_options \
    '*:: := _yo_scp_service'
}
local -a yo_scp_command=(/$'[^\0]#\0'/ ':yo-scp: :_yo_context _yo_scp_command' '#')

_yo_rsync_service() {
  _alternative \
    'yo-instances:instance:_yo_instances -S:' \
    ' : :{words[1]=rsync; _normal}'
}

_yo_rsync_command() {
  local -a _yo_rsync_options=(
    '--raw[Do not use the rsync_args stored in the config]'
  )

  _arguments -S \
    $_yo_rsync_options \
    $_yo_single_instance_options \
    '*:: := _yo_rsync_service'
}
local -a yo_rsync_command=(/$'[^\0]#\0'/ ':yo-rsync: :_yo_context _yo_rsync_command' '#')

_yo_console_command() {
  local -a _yo_console_options=(
    '--refresh[Refresh the local cache of serial consoles for this instance]'
  )

  _arguments -S \
    $_yo_console_options \
    $_yo_single_instance_options \
    '1:instance:_yo_instances'
}
local -a yo_console_command=(/$'[^\0]#\0'/ ':yo-console: :_yo_context _yo_console_command' '#')

_yo_copy_id_command() {
  local -a _yo_copy_id_options=(
    '(-i --identity-file)'{-i+,--identity-file=}'[Copy an ssh key to the instance with ssh-copy-id]'
  )

  _arguments -S \
    $_yo_copy_id_options \
    $_yo_single_instance_options \
    '1:instance:_yo_instances'
}
local -a yo_copy_id_command=(/$'[^\0]#\0'/ ':yo-copy-id: :_yo_context _yo_copy_id_command' '#')

local -a _yo_interactive_commands=(
  'ip:Print the IP address for one or more instances:$yo_ip_command'
  'scp:Copy files to/from an instance using the scp command:$yo_scp_command'
  'rsync:Synchronize files using the rsync command:$yo_rsync_command'
  'console:View an instance’s serial console using an SSH connection:$yo_console_command'
  'copy-id:Copy an SSH public key onto an instance using ssh-copy-id:$yo_copy_id_command'
  'console-history:Fetch and print serial console history for an instance:$yo_single_instance_command'
  'mosh:Connect to the instance via mosh:$yo_single_instance_command'
  'vnc:Connect to instance remote desktop using VNC:$yo_remote_desktop_command'
  'rdp:Connect to instance remote desktop using RDP:$yo_remote_desktop_command'
)
_regex_words yo-interactive-commands 'yo interactive command' $_yo_interactive_commands
local -a _yo_interactive=("$reply[@]")
# }}}
# yo task {{{
_yo_task_info_command() {
  integer n=2-${words[(I)task-*]}
  _arguments -S \
    $n':task:_yo_tasks'
}
local -a yo_task_info_command=(/$'[^\0]#\0'/ ':yo-task-info: :_yo_context _yo_task_info_command' '#')

_yo_task_run_command() {
  integer n=2-${words[(I)task-*]}
  local -a _yo_task_run_options=(
    '(-w --wait)'{-w,--wait}'[Wait until the task is finished]'
  )
  _arguments -S \
    $_yo_single_instance_options \
    $_yo_task_run_options \
    $n':instance:_yo_instances' \
      ':task:_yo_tasks'
}
local -a yo_task_run_command=(/$'[^\0]#\0'/ ':yo-task-run: :_yo_context _yo_task_run_command' '#')

_yo_task_wait_command() {
  integer n=2-${words[(I)task-*]}
  _arguments -S \
    $_yo_single_instance_options \
    $n':instance:_yo_instances' \
      ':task:_yo_tasks'
}
local -a yo_task_wait_command=(/$'[^\0]#\0'/ ':yo-task-wait: :_yo_context _yo_task_wait_command' '#')

_yo_task_single_instance_command() {
  integer n=2-${words[(I)task-*]}
  _arguments -S \
    $_yo_single_instance_options \
    $n':instance:_yo_instances'
}
local -a yo_task_single_instance_command=(/$'[^\0]#\0'/ ': : :_yo_context _yo_task_single_instance_command' '#')

local -a _yo_task_commands=(
  'info:Show the basic information and script contents for a task:$yo_task_info_command'
  'list:List every task and its basic metadata'
  'run:Run a long-running task script on an instance:$yo_task_run_command'
  'status:Report the status of all tasks on an instance:$yo_task_single_instance_command'
  'wait:Wait for a task to complete on an instance:$yo_task_single_instance_command'
  'join:Wait for all tasks on a given instance to complete:$yo_task_single_instance_command'
)
_regex_words yo-task-commands 'yo task command' $_yo_task_commands
local -a _yo_task=("$reply[@]")
local -a _yo_prefix_task_commands=(
  task-$^_yo_task_commands
  'task:Operate on a task:$_yo_task'
)
_regex_words yo-task-commands 'yo task command' $_yo_prefix_task_commands
local -a _yo_prefix_task=("$reply[@]")
# }}}
# yo volume {{{
local -a _yo_volume_attach_options=(
  '(-E --exact-name)'{-E,--exact-name}'[Do not prefix the instance name with your username]'
  '--no-exact-name[Always prefix the instance name with your username]'
  + '(volume-attach-setup)'
  '--ro[Attach volume read only]'
  '--shared[Attach volume in shared mode]'
  '--no-setup[Do not automatically run iSCSI setup commands]'
  + '(volume-attach-kind)'
  '--iscsi[Use an iSCSI attachment]'
  '--pv[Use a paravirtualized attachment]'
  '--emulated[Use an emulated attachment]'
  '--service-determined[Let OCI decide the attachment type]'
)

_yo_volume_create_command() {
  integer n=2-${words[(I)volume-*]}
  local -a _yo_volume_create_options=(
    '--ad=[availability domain]:availability domain:_yo_ads'
    '(-f --for)'{-f+,--for=}'[Which instance the volume is intended for]'
    '(-a --attach)'{-a,--attach}'[Attach to the instance after completion]'
  )
  _arguments -S $_yo_volume_create_options \
    $_yo_volume_attach_options \
    + -default- \
    $n':volume name:()' \
      ':size:()'
}
local -a yo_volume_create_command=(/$'[^\0]#\0'/ ':yo-volume-create: :_yo_context _yo_volume_create_command' '#')

_yo_volume_attach_command() {
  integer n=2-${words[(I)volume-*]}
  _arguments -S $_yo_volume_attach_options \
    '--as-boot[Attach as a boot volume]' \
    + -default- \
    $n':volume name:_yo_volumes' \
      ':instance name:_yo_instances'
}
local -a yo_volume_attach_command=(/$'[^\0]#\0'/ ':yo-volume-attach: :_yo_context _yo_volume_attach_command' '#')

_yo_volume_rename_command() {
  integer n=2-${words[(I)volume-*]}
  local -a _yo_volume_rename_options=(
    '(-n --exact-name)'{-n,--exact-name}'[Do not prefix the instance name with your username]'
  )
  _arguments -S $_yo_volume_rename_options \
    $n':old name:_yo_volumes' \
      ':new name:()'
}
local -a yo_volume_rename_command=(/$'[^\0]#\0'/ ':yo-volume-rename: :_yo_context _yo_volume_rename_command' '#')

local -a _yo_volume_detach_options=(
  '(-E --exact-name)'{-E,--exact-name}'[Do not prefix the instance name with your username]'
  '--no-exact-name[Always prefix the instance name with your username]'
  '--no-teardown[Do not run iSCSI teardown commands]'
  + '(volume-detach-which)'
  '--from=[Instance to detach from if there are multiple]:instance:_yo_instances'
  '--all[Detach from all instances]'
)

_yo_volume_detach_command() {
  integer n=2-${words[(I)volume-*]}
  _arguments -S $_yo_volume_detach_options \
    + volume\
    $n':volume:_yo_volumes'
}
local -a yo_volume_detach_command=(/$'[^\0]#\0'/ ':yo-volume-detach: :_yo_context _yo_volume_detach_command' '#')

_yo_volume_delete_command() {
  integer n=2-${words[(I)volume-*]}
  local -a _yo_volume_delete_options=(
    '(-D --no-detach)'{-D,--no-detach}'[Do not delete from all instances first]'
  )

  _arguments -S $_yo_volume_delete_options \
    $_yo_volume_detach_options \
    + volume \
    $n':name:_yo_volumes'
}
local -a yo_volume_delete_command=(/$'[^\0]#\0'/ ':yo-volume-delete: :_yo_context _yo_volume_delete_command' '#')

local -a _yo_volume_commands=(
  'list:List block and boot volumes'
  'attached:List volumes by their current instance attachment'
  'create:Create a block volume:$yo_volume_create_command'
  'attach:Attach a block or boot volume to an instance:$yo_volume_attach_command'
  'rename:Rename a block or boot volume:$yo_volume_rename_command'
  'detach:Detach a block or boot volume from an instance:$yo_volume_detach_command'
  'delete:Delete a block or boot volume:$yo_volume_delete_command'
)
_regex_words yo-volume-commands 'yo volume command' $_yo_volume_commands
local -a _yo_volume=("$reply[@]")
local -a _yo_volume_prefix_commands=(
  volume-$^_yo_volume_commands
  'vo*lume:Operate on a volume:$_yo_volume'
)
_regex_words yo-volume-commands 'yo volume command' $_yo_volume_prefix_commands
local -a _yo_prefix_volume=("$reply[@]")
# }}}
# yo info {{{

_yo_images_command() {
  local -a _yo_images_options=(
    '(-v --verbose)'{-v,--verbose}'[Print detailed image information]'
  )
  _arguments -S $_yo_images_options '1:image:_yo_images'
}
local -a yo_images_command=(/$'[^\0]#\0'/ ':yo-images: :_yo_context _yo_images_command' '#')

_yo_shapes_command() {
  local -a filters=(bm vm amd intel arm flex gpu disk)
  local -a _yo_shapes_options=(
    '(-v --verbose)'{-v,--verbose}'[Print detailed shape information]'
    '--cpu[Display detailed CPU information]'
    '--disk[Display details disk information]'
    '--gpu[Display detailed GPU information]'
    '(-a --availability)'{-a,--availability}'[Display availability across domains]'
    \*{-f+,--filter=}'[Filter to shapes with particular features]:filter:('"$filters"')'
  )
  _arguments -S -A '*' $_yo_shapes_options
}
local -a yo_shapes_command=(/$'[^\0]#\0'/ ':yo-shapes: :_yo_shapes_command' '#')

_yo_compat_command() {
  local -a _yo_compat_options=(
    '(-S --shape)'{-S+,--shape=}'[Shape name or pattern]'
    '--os=[OS name or pattern]'
    '--image=[Image name or pattern]:pattern:_yo_images'
    '--image-names=[Display the image name rather than the OS name]'
    '--width=[Width of column for shape names]'
  )
  _arguments -S -A '*' $_yo_compat_options
}
local -a yo_compat_command=(/$'[^\0]#\0'/ ':yo-compat: :_yo_compat_command' '#')

_yo_shape_command() { _arguments -S '1:shape:_yo_shapes' }
local -a yo_shape_command=(/$'[^\0]#\0'/ ':yo-shape: :_yo_context _yo_shape_command' '#')

_yo_limits_command()  {
  local -a _yo_limits_options=(
    '(-s --service)'{-s+,--service=}'[Service to inspect]:service:(compute block-storage)'
    '(-S --shape)'{-S+,--shape=}'[Shape to inspect]:shape:_yo_shapes'
  )
  _arguments -S -A '*' $_yo_limits_options
}
local -a yo_limits_command=(/$'[^\0]#\0'/ ':yo-limits: :_yo_limits_command' '#')

local -a _yo_info_commands=(
  'im*ages:List images available to use for launching an instance:$yo_images_command'
  'com*pat:Show a compatibility matrix of images and shapes:$yo_compat_command'
  'os:List official OS and version combinations'
  'shapes:List instance shape options:$yo_shapes_command'
  'shape:Get info about a single shape:$yo_shape_command'
  'lim*its:Display your tenancy and region’s service limits:$yo_limits_command'
)
_regex_words yo-info-commands 'yo info command' $_yo_info_commands
local -a _yo_info=("$reply[@]")
# }}}
# yo diagnostic {{{
local -a _yo_diagnostic_commands=(
  'debug:Open up a python prompt in the context of a command'
  'version:Show the version of yo and check for updates'
  'cache-clean:Clear Yo’s caches'
  'help:Show help for yo'
)
_regex_words yo-diagnostic-commands 'yo diagnostic command' $_yo_diagnostic_commands
local -a _yo_diagnostic=("$reply[@]")
# }}}

local gname
if zstyle -s ":completion:${curcontext}:" group-name gname; then
  _regex_arguments _yo_cmd /$'[^\0]#\0'/ \
    '(' "$_yo_basic[@]" '|'       \
      "$_yo_instance[@]" '|'      \
      "$_yo_interactive[@]" '|'   \
      "$_yo_prefix_task[@]" '|'   \
      "$_yo_prefix_volume[@]" '|' \
      "$_yo_instance[@]" '|'      \
      "$_yo_info[@]" '|'          \
      "$_yo_diagnostic[@]"        \
    ')'
else
  _regex_words yo-commands 'yo command' \
    $_yo_basic_commands \
    $_yo_instance_commands \
    $_yo_interactive_commands \
    $_yo_prefix_task_commands \
    $_yo_volume_prefix_commands \
    $_yo_info_commands \
    $_yo_diagnostic_commands

  _regex_arguments _yo_cmd /$'[^\0]#\0'/ "$reply[@]"
fi

_yo_prep_cmd() {
  # yuck
  local region_default_sed_pattern='/\[yo\]/,/^ *\[/ s/^ *region *= *([a-z0-9-]+)/\1/p'
  local region=${YO_REGION:-${(v)opt_args[(I)-r|--region]}}
  if [[ -z $region ]]; then
    region="$(_call_program -l yo-region-default sed -En ${(q)region_default_sed_pattern} ~/.oci/yo.ini)"
  fi
  local -a caches=( ~/.cache/yo.${region:-*}.json(N.) )

  _yo_cmd "$@"
}

# also yuck
local exact_name="$(_call_program -l yo-exact-name grep -E ${(q):-'^ *exact_name *= *true'} ~/.oci/yo.ini)"
local -a _yo_regions=(
  ${${(@f)"$(_call_program -l yo-regions grep -Eo ${(q):-'^ *\[regions.([a-z0-9-]+)'} ~/.oci/yo.ini)"}# #\[regions.}
)
local -a _yo_profiles=(
  ${${(@f)"$(_call_program -l yo-profiles grep -Eo ${(q):-'^ *\[instances.([a-z0-9-]+)'} ~/.oci/yo.ini)"}# #\[instances.}
)

local -a _yo_options=(
  '(-h --help)'{-h,--help}'[Show a help message and quit]'
  '(-r --region)'{-r+,--region=}'[Select an OCI region]:oci region:('"$_yo_regions"')'
)

_arguments -S $_yo_options '*:: := _yo_prep_cmd'

# vim: set sw=2 ts=2 fdm=marker et:
