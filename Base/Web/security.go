package main

import "net"

// Une IP venant du réseau (télémétrie) est utilisée dans des commandes ssh/scp :
// on n'accepte qu'une adresse IP littérale.
func isValidIP(s string) bool {
	return net.ParseIP(s) != nil
}
