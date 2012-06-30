# ============================================================
# bootstrap-button.js v2.0.1
# http://twitter.github.com/bootstrap/javascript.html#buttons
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
# ============================================================ */

do ($ = window.jQuery) ->

  class Button

    constructor: (element, options) ->
      @$element = $(element)
      @options = $.extend({}, $.fn.button.defaults, options)

    setState: (state) ->
      d = "disabled"
      $el = @$element
      data = $el.data()
      val = (if $el.is("input") then "val" else "html")
      state = state + "Text"
      data.resetText or $el.data("resetText", $el[val]())
      $el[val] data[state] or @options[state]
      setTimeout ->
          if state is "loadingText"
            $el.addClass(d).attr(d, d)
          else
            $el.removeClass(d).removeAttr(d)
        , 0

    toggle: ->
      $parent = @$element.parent("[data-toggle=\"buttons-radio\"]")
      $parent and $parent.find(".active").removeClass("active")
      @$element.toggleClass "active"

  $.fn.button = (option) ->
    @each ->
      $this = $(this)
      data = $this.data("button")
      options = typeof option is "object" and option
      $this.data "button", (data = new Button(this, options)) unless data
      if option is "toggle"
        data.toggle()
      else
        data.setState option if option

  $.fn.button.defaults = loadingText: "loading..."
  $.fn.button.Constructor = Button
  $ ->
    $("body").on "click.button.data-api", "[data-toggle^=button]", (e) ->
      $(e.currentTarget).button "toggle"
