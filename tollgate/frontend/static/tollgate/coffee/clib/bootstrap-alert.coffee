not ($) ->
  "use strict"
  dismiss = "[data-dismiss=\"alert\"]"
  Alert = (el) ->
    $(el).on "click", dismiss, @close

  Alert:: =
    constructor: Alert
    close: (e) ->
      removeElement = ->
        $parent.trigger("closed").remove()
      $this = $(this)
      selector = $this.attr("data-target")
      $parent = undefined
      unless selector
        selector = $this.attr("href")
        selector = selector and selector.replace(/.*(?=#[^\s]*$)/, "")
      $parent = $(selector)
      $parent.trigger "close"
      e and e.preventDefault()
      $parent.length or ($parent = (if $this.hasClass("alert") then $this else $this.parent()))
      $parent.trigger("close").removeClass "in"
      (if $.support.transition and $parent.hasClass("fade") then $parent.on($.support.transition.end, removeElement) else removeElement())

  $.fn.alert = (option) ->
    @each ->
      $this = $(this)
      data = $this.data("alert")
      $this.data "alert", (data = new Alert(this))  unless data
      data[option].call $this  if typeof option is "string"

  $.fn.alert.Constructor = Alert
  $ ->
    $("body").on "click.alert.data-api", dismiss, Alert::close
(window.jQuery)
