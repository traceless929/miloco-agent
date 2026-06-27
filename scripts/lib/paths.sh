#!/usr/bin/env bash
# Shared path resolution for miloco-agent fork scripts.
# shellcheck shell=bash

if [[ -n "${BASH_SOURCE[1]:-}" ]]; then
  _miloco_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
else
  _miloco_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
AGENT_ROOT="$(cd "$_miloco_scripts_dir/.." && pwd)"
MILOCO_REPO="${MILOCO_REPO:-$(cd "$AGENT_ROOT/.." && pwd)}"
export AGENT_ROOT MILOCO_REPO
