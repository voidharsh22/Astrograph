package com.acme.model

class User(val name: String) : Base(), Svc {
    override fun run() {
    }

    fun greet(who: String): String {
        return "hi " + who
    }

    suspend fun load(): String {
        return greet("x")
    }

    companion object {
        fun create(): User = User("made")
    }
}

data class Point(val x: Int, val y: Int)

object Registry {
    fun size(): Int = 0
}

fun String.shout(): String = this.uppercase()

fun helper(u: User) {
    u.run()
}
