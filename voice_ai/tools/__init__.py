"""PC action center: the assistant's hands and eyes.

Tools the LLM (and the fast-path intent) may use, guarded by an
allowlist and fully audited:

    always on   web_search, read_page, open_url, open_app, sys_info,
                list_dir
    opt-in      run_command (arbitrary shell) — only with VIA_SHELL=1

Every execution is logged to the event stream with its arguments, so
users can see exactly what the assistant did on their machine.
"""
