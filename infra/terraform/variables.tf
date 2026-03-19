variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "node_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.medium"
}

variable "db_password" {
  type      = string
  sensitive = true
}
