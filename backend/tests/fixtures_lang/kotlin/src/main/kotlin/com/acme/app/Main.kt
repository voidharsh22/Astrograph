package com.acme.app

import com.acme.model.User
import com.acme.model.Svc as Service
import com.acme.model.helper
import com.acme.model.Registry

fun main() {
    val u = User("a")
    u.greet("b")
    u.id()
    User.create()
    helper(u)
    val s: Service = u
    s.run()
    Registry.size()
    println("done")
    missing(1)
}
