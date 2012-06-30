# ============================================================
# bootstrap-dropdown.js v2.0.1
# http://twitter.github.com/bootstrap/javascript.html#dropdowns
# ============================================================
# Copyright 2012 Twitter, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================

do ($ = window.jQuery) ->

  # DROPDOWN CLASS DEFINITION
  # =========================

  toggle = "[data-toggle=dropdown]"
  clearMenus = -> $(toggle).parent().removeClass "open"

  class Dropdown

    constructor: (element) ->
      $el = $(element).on("click.dropdown.data-api", @toggle)
      $("html").on "click.dropdown.data-api", ->
        $el.parent().removeClass "open"

    toggle: (e) ->
      $this    = $(this)
      selector = $this.attr("data-target")
      $parent  = undefined
      isActive = undefined
      unless selector
        selector = $this.attr("href")
        selector = selector.replace(/.*(?=#[^\s]*$)/, "") if selector
      $parent = $this.parent() if $parent.length else $(selector)
      isActive = $parent.hasClass("open")
      clearMenus()
      not isActive and $parent.toggleClass("open")
      false

  $.fn.dropdown = (option) ->
    @each ->
      $this = $(this)
      data = $this.data("dropdown")
      $this.data "dropdown", (data = new Dropdown(this))  unless data
      data[option].call $this if typeof option is "string"

  $.fn.dropdown.Constructor = Dropdown
  $ ->
    $("html").on "click.dropdown.data-api", clearMenus
    $("body").on "click.dropdown.data-api", toggle, Dropdown::toggle
