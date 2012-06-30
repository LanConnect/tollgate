# ==========================================================
# bootstrap-carousel.js v2.0.1
# http://twitter.github.com/bootstrap/javascript.html#carousel
# ==========================================================
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
# ==========================================================

do ($ = window.jQuery) ->

  # CAROUSEL CLASS DEFINITION
  # =========================

  class Carousel

    constructor: (element, options) ->
      @$element = $(element)
      @options  = $.extend {}, $.fn.carousel.defaults, options
      @slide( @options.slide ) if @options.slide

    to: (pos) ->
      $active   = @$element.find(".active")
      children  = $active.parent().children()
      activePos = children.index($active)

      return if pos > (children.length - 1) or pos < 0

      if @sliding
        return @$element.one "slid", => @to pos

      if pos is activePos
        return @pause().cycle()

      return @slide (if pos > activePos then 'next' else 'prev')
                  , $(children[pos])

    pause: ->
      clearInterval @interval
      @interval = null
      return @

    next: ->
      return if @sliding
      return this.slide 'next'

    prev: ->
      return if @sliding
      return this.slide 'prev'

    slide: (type, next) ->
      $active   = @$element.find '.active'
      $next     = next || $active[type]()
      isCycling = @interval
      direction = if type is 'next' then 'left'  else 'right'
      fallback  = if type is 'next' then 'first' else 'last'

      @sliding  = true

      @pause if isCycling

      $next = if $next.length
                $next
              else
                @$element.find('.item')[fallback]()

      if not $.support.transition and @$element.hasClass("slide")
        @$element.trigger "slide"
        $active.removeClass "active"
        $next.addClass "active"
        @sliding = false
        @$element.trigger "slid"
      else
        $next.addClass type
        $next[0].offsetWidth
        $active.addClass direction
        $next.addClass direction
        @$element.trigger "slide"
        @$element.one $.support.transition.end, =>
          $next.removeClass([ type, direction ].join(" ")).addClass "active"
          $active.removeClass [ "active", direction ].join(" ")
          @sliding = false
          setTimeout (=> @$element.trigger "slid") , 0

      @cycle if isCycling

      return this

  # CAROUSEL PLUGIN DEFINITION
  # ==========================

  $.fn.carousel = (option) ->
    @each ->
      $this = $(this)
      data = $this.data("carousel")
      options = typeof option is "object" and option
      $this.data "carousel", (data = new Carousel(this, options)) unless data
      if typeof option is "number"
        data.to option
      else if typeof option is "string" or (option = options.slide)
        data[option]()
      else
        data.cycle()

  $.fn.carousel.Class = Carousel
  $.fn.carousel.defaults =
    interval: 5000

  # CAROUSEL DATA-API
  # =================

  $ ->
    $("body").on "click.carousel.data-api", "[data-slide]", (e) ->
      $this = $(this)
      href = undefined
      $target = $($this.attr("data-target") or (href = $this.attr("href")) and href.replace(/.*(?=#[^\s]+$)/, ""))
      options = !$target.data("modal") and $.extend({}, $target.data(), $this.data())
      $target.carousel options
      e.preventDefault()
